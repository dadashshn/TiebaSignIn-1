#!/usr/bin/env python3
"""百度贴吧自动签到 - GitHub Actions 入口

用法:
    python run.py                          # 自动读取环境变量 BDUSS
    python run.py --bduss "your_bduss"     # 命令行传入 BDUSS
"""

import argparse
import logging
import os
import random
import time
# ... 原有 import ...
import hashlib
import hmac
import base64
import urllib.parse
import json
import requests  # 需确保环境中已安装 requests

# ========== 【在此处添加钉钉配置】 ==========
# 推荐：从环境变量读取（GitHub Actions 中在 Secrets 里配置）
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "你的Webhook地址")
DINGTALK_SECRET = os.environ.get("DINGTALK_SECRET", "你的加签密钥SEC开头")
# ==========================================

from tieba_client import TiebaClient

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> str:
    parser = argparse.ArgumentParser(description="百度贴吧自动签到")
    parser.add_argument(
        "--bduss",
        default=None,
        help="贴吧 BDUSS Cookie 值（优先级高于环境变量）",
    )
    args = parser.parse_args()

    bduss = args.bduss or os.environ.get("BDUSS", "")
    if not bduss:
        parser.error("请通过 --bduss 参数或 BDUSS 环境变量提供 BDUSS")
    return bduss

def send_dingtalk_notification(title: str, text: str) -> None:
    """发送钉钉机器人通知（带加签验证）"""
    if not DINGTALK_WEBHOOK or not DINGTALK_SECRET:
        logger.warning("未配置钉钉 Webhook 或 Secret，跳过通知")
        return

    try:
        # 生成加签参数
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{DINGTALK_SECRET}"
        hmac_code = hmac.new(
            DINGTALK_SECRET.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

        # 拼接完整 URL
        url = f"{DINGTALK_WEBHOOK}&timestamp={timestamp}&sign={sign}"

        # 构造 Markdown 消息体
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text},
        }

        resp = requests.post(url, json=payload, timeout=10)
        result = resp.json()

        if result.get("errcode") == 0:
            logger.info("钉钉通知发送成功")
        else:
            logger.error(f"钉钉通知发送失败: {result}")
    except Exception as e:
        logger.error(f"钉钉通知异常: {e}")

def main() -> None:
    bduss = parse_args()
    client = TiebaClient(bduss)

    # 1. 获取 tbs
    logger.info("正在获取 tbs...")
    tbs = client.get_tbs()
    if tbs is None:
        logger.error("获取 tbs 失败，退出")
        raise SystemExit(1)

    # 2. 获取关注的贴吧列表
    logger.info("正在获取关注的贴吧列表...")
    forums = client.get_favorites()
    if not forums:
        logger.warning("未获取到关注的贴吧，签到结束")
        return

    # 3. 逐个签到 (带节流)
    total = len(forums)
    logger.info(f"开始签到 {total} 个贴吧")

    stats = {"success": 0, "exist": 0, "shield": 0, "error": 0}
    for idx, forum in enumerate(forums):
        # 节流: 随机间隔 1.0-2.5 秒
        delay = random.uniform(1.0, 2.5)
        time.sleep(delay)

        # 每 10 个贴吧额外休息 5-10 秒
        if (idx + 1) % 10 == 0:
            extra = random.uniform(5, 10)
            logger.info(f"已签到 {idx + 1}/{total} 个，休息 {extra:.1f}s ...")
            time.sleep(extra)

        fid = forum.get("id", "")
        fname = forum.get("name", "")
        result = client.sign_forum(fid, fname, tbs)
        stats[result["status"]] += 1

        # 打印单条结果
        prefix = f"【{fname}】({idx + 1}/{total})"
        if result["status"] == "success":
            rank_str = f"，第 {result['rank']} 个签到" if result["rank"] else ""
            logger.info(f"{prefix} 签到成功{rank_str}")
        elif result["status"] == "exist":
            logger.info(f"{prefix} {result['message']}")
        elif result["status"] == "shield":
            logger.warning(f"{prefix} {result['message']}")
        else:
            logger.error(f"{prefix} 签到失败: {result['message']}")

    # 4. 汇总
    summary = (
        f"\n========== 签到汇总 ==========\n"
        f"贴吧总数: {total}\n"
        f"签到成功: {stats['success']}\n"
        f"已经签到: {stats['exist']}\n"
        f"被屏蔽的: {stats['shield']}\n"
        f"签到失败: {stats['error']}\n"
        f"================================"
    )
    logger.info(summary)


    # ========== 【在此处调用钉钉通知】 ==========
    send_dingtalk_notification("贴吧签到汇总", summary)
    # ==========================================

if __name__ == "__main__":
    main()
