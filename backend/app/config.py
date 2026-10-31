"""配置加载:读取 config.yaml 并展开 ${ENV_NAME} 形式的环境变量占位符"""
import os
import re
from pathlib import Path
from types import SimpleNamespace

import yaml
from loguru import logger

# 匹配 ${ENV_NAME} 形式的环境变量占位符
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# config.yaml 固定在 app 包目录下
_CONFIG_PATH = Path(__file__).parent / "config.yaml"
# 配置里的相对路径统一以 backend 目录为基准,不依赖启动时的工作目录
_BACKEND_DIR = _CONFIG_PATH.parent.parent


def _expand_env_vars(value):
    """递归展开配置中的 ${ENV_NAME} 占位符,未设置的环境变量替换为空字符串"""
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(v) for v in value]
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)
    return value


def _dict_to_namespace(obj):
    """递归把 dict 转成支持属性访问的 SimpleNamespace"""
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _dict_to_namespace(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_dict_to_namespace(v) for v in obj]
    return obj


def load_config() -> SimpleNamespace:
    """加载并返回全局配置对象"""
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        raise RuntimeError(f"配置文件为空: {_CONFIG_PATH}")

    data = _expand_env_vars(data)
    config = _dict_to_namespace(data)

    # 相对路径按 backend 目录解析,保证从任意目录启动都指向同一份向量库
    if not Path(config.rag.chroma_path).is_absolute():
        config.rag.chroma_path = str(_BACKEND_DIR / config.rag.chroma_path)

    # 必填连接配置缺失时直接报错,避免空 URL 传到下游报难以理解的解析错误
    for name, value in (("MYSQL_ENDPOINT", config.mysql.endpoint),
                        ("REDIS_ENDPOINT", config.redis.endpoint)):
        if not value:
            raise RuntimeError(
                f"未设置环境变量 {name}(格式见 config.yaml 注释);"
                "若刚设置过,请重开终端或重启 IDE 使新环境变量生效"
            )

    if not config.models.chat.api_key:
        logger.warning("未读取到 DASHSCOPE_API_KEY 环境变量,模型调用会失败")
    return config


# 全局单例
settings = load_config()
