#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外部题库快速配置与测试脚本

使用方式：
  python setup_external_qbank.py --configure
  python setup_external_qbank.py --test "https://api.example.com/questions" "api_key"
  python setup_external_qbank.py --check
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Dict, Tuple

import httpx


def configure_env() -> None:
    """交互式配置环境变量（柠檬题库 / LIKE知识库 同款查题接口）"""
    print("\n" + "=" * 80)
    print("外部查题题库配置向导")
    print("文档: https://docs.lemtk.xyz/get-started.html")
    print("=" * 80)

    # 获取配置信息
    api_url = input("\n请输入题库域名 (默认 https://api.lemtk.xyz，备用 https://api.vanse.top):\n> ").strip() or "https://api.lemtk.xyz"
    api_key = input("\n请输入 Token（普通查询可留空；高级查询必填）:\n> ").strip()
    email = input("\n请输入注册邮箱（仅余额查询使用，可留空）:\n> ").strip()
    mode = input("\n查询模式 cx=普通 / mcx=高级 (默认 cx):\n> ").strip() or "cx"
    timeout = input("\n请输入请求超时时间（秒，默认 8）:\n> ").strip() or "8"

    # 验证输入
    if not api_url.startswith("http"):
        print("❌ 错误：题库域名必须以 http:// 或 https:// 开头")
        return

    try:
        float(timeout)
    except ValueError:
        print("❌ 错误：超时时间必须是数字")
        return

    # 查找 .env 文件
    env_files = [
        Path(".env"),
        Path("backend/.env"),
        Path("../.env"),
    ]

    env_path = None
    for f in env_files:
        if f.exists():
            env_path = f
            break

    if not env_path:
        print("\n📝 未找到 .env 文件，创建新文件：.env")
        env_path = Path(".env")

    # 读取现有配置
    existing_config = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                existing_config[key.strip()] = value.strip()

    # 更新配置
    existing_config["QBANK_BASE_URL"] = api_url
    existing_config["QBANK_TOKEN"] = api_key
    existing_config["QBANK_EMAIL"] = email
    existing_config["QBANK_MODE"] = mode if mode in ("cx", "mcx") else "cx"
    existing_config["QBANK_TIMEOUT"] = timeout

    # 写入 .env 文件
    content = "\n".join(f"{k}={v}" for k, v in existing_config.items())
    env_path.write_text(content)

    print(f"\n✓ 配置已保存到 {env_path}")
    print(f"\n配置内容：")
    print(f"  QBANK_BASE_URL={api_url}")
    print(f"  QBANK_TOKEN={'*' * len(api_key) if api_key else '(未设置，免费限流通道)'}")
    print(f"  QBANK_EMAIL={email or '(未设置)'}")
    print(f"  QBANK_MODE={existing_config['QBANK_MODE']}")
    print(f"  QBANK_TIMEOUT={timeout}")


async def test_connection(api_url: str, api_key: str = "") -> Tuple[bool, Dict]:
    """测试外部题库 API 连通性"""
    
    print(f"\n测试连接: {api_url}")
    
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    # 构造测试请求
    payload = {
        "exam_name": "TEST",
        "knowledge_point": "测试",
        "module": "测试",
        "count": 1,
        "language": "zh",
        "question_type": "single_choice",
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                api_url,
                headers=headers,
                json=payload,
            )
        
        if response.status_code == 200:
            data = response.json()
            questions = data.get("questions", [])
            
            return True, {
                "status": "connected",
                "http_status": response.status_code,
                "questions_received": len(questions),
                "response_time_ms": response.elapsed.total_seconds() * 1000,
            }
        else:
            return False, {
                "status": "http_error",
                "http_status": response.status_code,
                "error": response.text[:200],
            }
    
    except Exception as e:
        return False, {
            "status": "connection_error",
            "error": str(e),
        }


def check_configuration() -> None:
    """检查当前配置"""
    print("\n" + "=" * 80)
    print("查题题库配置检查")
    print("=" * 80)

    # 尝试读取 .env 文件
    env_files = [Path(".env"), Path("backend/.env"), Path("../.env")]
    env_path = None
    config = {}

    for f in env_files:
        if f.exists():
            env_path = f
            for line in f.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
            break

    print(f"\n配置文件: {env_path or '未找到'}")

    if not config:
        print("\n❌ 未找到任何配置")
        return

    provider = (config.get("QBANK_PROVIDER") or "lemtk").lower()

    if provider in ("gomooc", "zero", "zerobank"):
        base = config.get("QBANK_GOMOOC_BASE_URL") or "https://api.gomooc.net"
        path = config.get("QBANK_GOMOOC_ENDPOINT") or "/api.php"
        token = config.get("QBANK_GOMOOC_TOKEN") or config.get("QBANK_TOKEN") or ""
        merge = config.get("QBANK_GOMOOC_MERGE_OPTIONS", "true")
        print("\n当前供应商: gomooc（ZERO 网课题库）")
        print(f"  QBANK_GOMOOC_BASE_URL: {base}")
        print(f"  QBANK_GOMOOC_ENDPOINT: {path}")
        print(f"  QBANK_GOMOOC_TOKEN: {('✓ ' + '*' * len(token)) if token else '❌ 未配置（该接口必须带 token）'}")
        print(f"  QBANK_GOMOOC_MERGE_OPTIONS: {merge}")
        print(f"  QBANK_TIMEOUT: {config.get('QBANK_TIMEOUT', '8')}s")
        if token:
            print("\n✓ ZERO 题库已配置；额度用尽时查题会返回 code 429（剩余次数: 0）")
        else:
            print("\n❌ ZERO 题库缺少 token，查题会直接返回 1002（token为空）")
        return

    # 显示配置（新变量优先，兼容旧变量）
    api_url = config.get("QBANK_BASE_URL") or config.get("QUESTION_BANK_API_URL", "")
    api_key = config.get("QBANK_TOKEN") or config.get("QUESTION_BANK_API_KEY", "")
    email = config.get("QBANK_EMAIL", "")
    mode = config.get("QBANK_MODE", "cx")
    timeout = config.get("QBANK_TIMEOUT") or config.get("QUESTION_BANK_TIMEOUT", "8")

    print("\n当前供应商: lemtk（柠檬题库）")
    print(f"\n检测到的配置：")
    print(f"  QBANK_BASE_URL: {api_url if api_url else '❌ 未配置'}")
    print(f"  QBANK_TOKEN: {('✓ ' + '*' * len(api_key)) if api_key else '❌ 未配置（免费限流通道）'}")
    print(f"  QBANK_EMAIL: {email or '❌ 未配置（余额查询不可用）'}")
    print(f"  QBANK_MODE: {mode}")
    print(f"  QBANK_TIMEOUT: {timeout}s")

    if api_url:
        print(f"\n✓ 查题题库已配置（{'高级查询' if mode == 'mcx' else '普通查询'}）")
    else:
        print(f"\n❌ 查题题库未配置，将使用内置题库")


async def test_balance() -> None:
    """测试题库余额查询（GET /api/v1/balance）"""
    print("\n" + "=" * 80)
    print("题库余额查询测试")
    print("=" * 80)

    try:
        from app.services.qbank_chaoxing import ChaoxingQBankAdapter
    except ImportError:
        print("❌ 无法导入题库适配器，请确保在 backend 目录执行此脚本")
        return

    adapter = ChaoxingQBankAdapter()
    result = await adapter.check_balance()
    await adapter.close()

    print(f"\n状态：{result.get('status')}")
    print(f"详情：{result.get('detail')}")
    if result.get("status") == "ok":
        print(f"余额：{result.get('balance')} 点")
        print(f"账号：{result.get('email')}")
        print(f"封禁标记：{result.get('banned')}")
    else:
        print("❌ 余额查询未成功")


async def test_chaoxing_adapter() -> None:
    """测试查题适配器：先试余额，再做一道样例题"""
    print("\n" + "=" * 80)
    print("第三方查题题库 API 测试")
    print("文档: https://docs.lemtk.xyz/get-started.html")
    print("=" * 80)

    # 导入适配器
    try:
        from app.services.qbank_chaoxing import ChaoxingQBankAdapter, SUPPORTED_PLATFORMS
    except ImportError:
        print("❌ 无法导入题库适配器，请确保在 backend 目录执行此脚本")
        return

    print(f"\n支持平台标签：")
    for code, name in SUPPORTED_PLATFORMS.items():
        print(f"  • {code:12} - {name}")

    # 测试配置
    adapter = ChaoxingQBankAdapter()

    print(f"\n当前配置：")
    print(f"  域名: {adapter.base_url}")
    print(f"  Token: {'✓ 已配置' if adapter.token else '❌ 未配置（免费限流通道）'}")
    print(f"  邮箱: {adapter.email or '❌ 未配置'}")
    print(f"  模式: {adapter.mode}")
    print(f"  超时: {adapter.timeout}s")

    # 余额查询（需要 Token + 邮箱）
    print(f"\n—— 余额查询 ——")
    balance = await adapter.check_balance()
    print(f"  状态：{balance.get('status')}")
    print(f"  详情：{balance.get('detail')}")
    if balance.get("status") == "ok":
        print(f"  余额：{balance.get('balance')} 点")

    # 样例题查题
    print(f"\n—— 样例题查题 ——")
    metadata = await adapter.lookup(
        question="设函数 f(x)=x²，则 f(x) 在 x=1 处的导数为",
        question_type="single_choice",
        options=["0", "1", "2", "3"],
    )
    print(f"  状态：{metadata.get('status')}")
    print(f"  延迟：{metadata.get('latency_ms')}ms")
    print(f"  详情：{metadata.get('detail')}")
    if metadata.get("answer_texts"):
        print(f"  答案文本：{metadata['answer_texts']}")
        print(f"  答案下标：{metadata.get('answer_indexes')}")

    await adapter.close()


async def test_zero_adapter() -> None:
    """测试 ZERO 网课题库（api.gomooc.net/api.php）真实查题。"""
    print("\n" + "=" * 80)
    print("ZERO 网课题库 API 测试")
    print("接口: GET /api.php?token=<token>&question=<题干>")
    print("=" * 80)

    try:
        from app.services.qbank_gomooc import GomoocQBankAdapter
    except ImportError:
        print("❌ 无法导入 ZERO 题库适配器，请确保在 backend 目录执行本脚本")
        return

    adapter = GomoocQBankAdapter()
    print("\n当前配置：")
    print(f"  接口地址: {adapter.lookup_url or '(未配置)'}")
    print(f"  Token: {'✓ 已配置' if adapter.token else '❌ 未配置'}")
    print(f"  超时: {adapter.timeout}s")

    metadata = await adapter.lookup(
        question="设函数 f(x)=x²，则 f(x) 在 x=1 处的导数为",
        question_type="single_choice",
        options=["0", "1", "2", "3"],
    )
    print("\n—— 样例题查题 ——")
    print(f"  状态: {metadata.get('status')}")
    print(f"  延迟: {metadata.get('latency_ms')}ms")
    print(f"  详情: {metadata.get('detail')}")
    if metadata.get("answer_texts"):
        print(f"  答案文本: {metadata['answer_texts']}")
        print(f"  答案下标: {metadata.get('answer_indexes')}")

    await adapter.close()


async def main():
    """主函数"""
    
    parser = argparse.ArgumentParser(
        description="外部题库配置和测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 交互式配置
  python setup_external_qbank.py --configure
  
  # 测试连接
  python setup_external_qbank.py --test https://api.example.com/questions api_key_here
  
  # 检查配置
  python setup_external_qbank.py --check
  
  # 测试 Chaoxing 适配器
  python setup_external_qbank.py --test-chaoxing

  # 测试 ZERO 网课题库
  python setup_external_qbank.py --test-zero
        """,
    )
    
    parser.add_argument(
        "--configure",
        action="store_true",
        help="交互式配置外部题库",
    )
    
    parser.add_argument(
        "--test",
        nargs=2,
        metavar=("URL", "API_KEY"),
        help="测试外部题库 API 连通性",
    )
    
    parser.add_argument(
        "--check",
        action="store_true",
        help="检查当前配置",
    )
    
    parser.add_argument(
        "--test-chaoxing",
        action="store_true",
        help="测试第三方查题题库适配器（余额 + 样例题）",
    )

    parser.add_argument(
        "--balance",
        action="store_true",
        help="查询题库剩余点数（需 QBANK_TOKEN 与 QBANK_EMAIL）",
    )

    parser.add_argument(
        "--test-zero",
        action="store_true",
        help="测试 ZERO 网课题库（api.gomooc.net/api.php）真实查题",
    )

    args = parser.parse_args()

    if args.configure:
        configure_env()

    elif args.test:
        api_url, api_key = args.test
        success, result = await test_connection(api_url, api_key)

        print("\n测试结果：")
        print("-" * 80)

        if success:
            print("✓ 连接成功！")
            print(f"  HTTP 状态码：{result['http_status']}")
            print(f"  返回题数：{result['questions_received']}")
            print(f"  响应时间：{result['response_time_ms']:.1f}ms")
        else:
            print("❌ 连接失败！")
            print(f"  状态：{result['status']}")
            print(f"  错误：{result.get('error', result.get('http_status', 'Unknown'))}")

    elif args.check:
        check_configuration()

    elif args.balance:
        await test_balance()

    elif args.test_chaoxing:
        await test_chaoxing_adapter()

    elif args.test_zero:
        await test_zero_adapter()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # 默认检查配置
        check_configuration()
    else:
        asyncio.run(main())
