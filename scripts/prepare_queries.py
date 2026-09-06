"""Explicit provisional judgments: never substitute for maintainer labels."""

import json
from pathlib import Path

PAIRS = [
    (
        "rtk.shell_output_proxy",
        "dev",
        "Сократить вывод команд для AI агента",
        "Reduce shell output for an AI coding agent",
    ),
    (
        "openai.codex",
        "dev",
        "Локальный агент для правки кода",
        "Local agent that edits repository code",
    ),
    (
        "axios.http_client",
        "dev",
        "HTTP клиент для браузера и Node",
        "HTTP client for browser and Node",
    ),
    (
        "bitcoin.core.fullnode",
        "dev",
        "Запустить полностью проверяющий узел Bitcoin",
        "Run a fully validating Bitcoin node",
    ),
    (
        "n8n.platform",
        "dev",
        "Визуальная автоматизация рабочих процессов",
        "Visual workflow automation",
    ),
    (
        "rtk.shell_output_proxy",
        "test",
        "Переписать shell команду в компактный вывод",
        "Rewrite shell commands for compact output",
    ),
    (
        "openai.codex",
        "test",
        "Встроить coding agent через TypeScript SDK",
        "Embed a coding agent through a TypeScript SDK",
    ),
    (
        "axios.http_client",
        "test",
        "Отменять HTTP запросы и настраивать таймауты",
        "Cancel HTTP requests and configure timeouts",
    ),
    (
        "bitcoin.core.fullnode",
        "test",
        "Управлять кошельком узла через RPC",
        "Manage a node wallet through RPC",
    ),
    (
        "n8n.platform",
        "test",
        "Настроить AI инструменты платформы автоматизации",
        "Configure AI tools for a workflow platform",
    ),
    ("rtk.shell_output_proxy", "test", "rtk.shell_output_proxy", "rtk.shell_output_proxy"),
    ("openai.codex", "test", "openai.codex", "openai.codex"),
    ("axios.http_client", "dev", "axios.http_client", "axios.http_client"),
    ("bitcoin.core.fullnode", "test", "bitcoin.core.fullnode", "bitcoin.core.fullnode"),
    ("n8n.platform", "dev", "n8n.platform", "n8n.platform"),
    (None, "dev", "Симуляция ядерного реактора", "Simulate a nuclear reactor"),
    (None, "dev", "Драйвер микроскопа для USB", "USB microscope device driver"),
    (None, "test", "Распознавание опухолей на МРТ", "Detect tumors in MRI scans"),
    (None, "test", "Прошивка для управления спутником", "Satellite attitude control firmware"),
    (None, "test", "Расчет орбит экзопланет", "Calculate exoplanet orbits"),
]


def main():
    rows = []
    for i, (package, split, ru, en) in enumerate(PAIRS):
        for language, text in (("ru", ru), ("en", en)):
            rows.append(
                {
                    "id": f"q{i:02}-{language}",
                    "group": f"q{i:02}",
                    "language": language,
                    "split": split,
                    "query": text,
                    "relevance": {package: 2} if package else {},
                    "negative": package is None,
                }
            )
    Path("eval/queries.json").write_text(
        json.dumps(
            {"version": 1, "labels_status": "provisional", "reviewer": None, "queries": rows},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
