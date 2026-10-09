"""Interactive terminal chat with the support agent."""

import uuid

from support_agent.service import run_turn


def main() -> None:
    thread_id = f"cli-{uuid.uuid4().hex[:8]}"
    print(f"Support agent ready (thread {thread_id}). Type 'exit' to quit.")

    while True:
        try:
            message = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if message.lower() in {"exit", "quit"}:
            break
        if not message:
            continue

        result = run_turn(message, thread_id)
        print(f"\nAgent: {result.reply}")
        print(
            f"  [intent={result.intent} | sentiment={result.sentiment} | tools={result.tools_used}]"
        )


if __name__ == "__main__":
    main()
