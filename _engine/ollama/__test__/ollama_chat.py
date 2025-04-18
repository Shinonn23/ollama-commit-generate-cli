import json
from _data.ollama import SYSTEM_PROMPT, BASE_URL
from _types.model import FileChange
import requests


content = """
diff --git a/main.py b/main.py
index e29d86d..92d59ef 100644
--- a/main.py
+++ b/main.py
@@ -326,6 +326,41 @@ def select_model(models) -> str | None:
        return select_model(models)


+def ask_question(model_name, prompt) -> None:
+   Send a question to the model and display the answer
+    data = {
+        "model": model_name,
+        "prompt": prompt,
+        "stream": False,
+    }
+
+    try:
+        with Progress(
+            SpinnerColumn(),
+            TextColumn(f"[bold blue]Thinking ({model_name})..."),
+            transient=True,
+        ) as progress:
+            progress.add_task("", total=None)
+            response = requests.post(f"{BASE_URL}/generate", json=data)
+
+        if response.status_code == 200:
+            result = response.json()
+            console.print(
+                Panel(
+                    Markdown(result.get("response", "No answer")),
+                    title=f"[bold green]Answer from {model_name}",
+                    border_style="green",
+                )
+            )
+        else:
+            console.print(f"[bold red]Error: {response.status_code}")
+    except requests.exceptions.ConnectionError:
+        console.print("[bold red]Unable to connect to Ollama server").print(
+            "[yellow]Please check if Ollama is running at http://localhost:11434"
+        )
+        return []
+
+
def analyze_diff_with_llm(
    model_name: str, diff_file: str, system_prompt: str = None
) -> str:
@@ -489,6 +524,7 @@ def main() -> None:
        "--threads", type=int, default=4, help="Number of parallel workers (default: 4)"
    )
    parser.add_argument("--prompt", help="Custom system prompt for the LLM")
+    parser.add_argument("-p", "--question", help="Specify question to ask (for direct question mode)")

    args = parser.parse_args()

@@ -509,6 +545,16 @@ def main() -> None:
    if not models:
        return

+    # Check if we're in question mode or diff analysis mode
+    if args.question:
+        if args.model:
+            ask_question(args.model, args.question)
+        else:
+            selected_model = select_model(models)
+            if selected_model:
+                ask_question(selected_model, args.question)
+        return
+
    # Get commit hash if not provided
    commit_hash = args.commit
    if not commit_hash:
@@ -516,8 +562,9 @@ def main() -> None:
        console.print("\n[bold yellow]What would you like to analyze?")
        console.print("[cyan]1. Current uncommitted changes")
        console.print("[cyan]2. Specific git commit")
+        console.print("[cyan]3. Ask a question to the model")
        choice = Prompt.ask(
-            "[bold cyan]Choose an option", choices=["1", "2"], default="1"
+            "[bold cyan]Choose an option", choices=["1", "2", "3"], default="1"
        )

        if choice == "2":
@@ -526,6 +573,16 @@ def main() -> None:
            commit_hash = Prompt.ask(
                "[bold cyan]Enter commit hash", default=latest_commit
            )
+        elif choice == "3":
+            # Direct question mode
+            selected_model = select_model(models)
+            while True:
+                prompt = console.input("\n[bold yellow]Question (type 'q' to quit): ")
+                if prompt.lower() == "q":
+                    break
+                if prompt:
+                    ask_question(selected_model, prompt)
+            return

# Let user select a model
selected_model = args.model or select_model(models)
"""


def git_generate(content: str):
    # Set stream=True to handle streaming response properly
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "model": "deepseek-r1:1.5b",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.strip()},
                {"role": "user", "content": content.strip()},
            ],
            "stream": True,  # Enable streaming
            "format": FileChange.model_json_schema(),
        },
    )

    if response.status_code == 200:
        try:
            # For streaming responses, we need to collect all the content
            full_content = ""
            
            print("Receiving streaming response...")
            for line in response.iter_lines():
                if line:
                    # Decode the line and parse it as JSON
                    chunk = json.loads(line.decode('utf-8'))
                    if "message" in chunk and "content" in chunk["message"]:
                        # Append the content from this chunk
                        full_content += chunk["message"]["content"]
                    
                    # Check if this is the final chunk
                    if chunk.get("done", False):
                        break
            
            print(f"Received complete response, length: {len(full_content)} characters")
            
            # Now try to parse the complete content as JSON
            try:
                # The full_content should be a valid JSON string
                parsed_response = FileChange.model_validate_json(full_content)
                
                # Save the parsed response to a file
                with open(
                    "temp_diffs/ollama_response_optimized.json", "w", encoding="utf-8"
                ) as f:
                    f.write(
                        json.dumps(parsed_response.model_dump(), indent=2, ensure_ascii=False)
                    )
                print("✅ Optimized response saved to ollama_response_optimized.json")
            except json.JSONDecodeError as e:
                print(f"❌ Error parsing complete response as JSON: {e}")
                print(f"Content received: {full_content[:500]}...")
            except Exception as e:
                print(f"❌ Error processing complete response: {e}")
                
        except Exception as e:
            print(f"❌ Error handling streaming response: {e}")
    else:
        print(f"❌ Error from API: {response.status_code} - {response.text}")


if __name__ == "__main__":
    git_generate(content)
