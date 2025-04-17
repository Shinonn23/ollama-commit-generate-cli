from rich.console import Console
import time

console = Console()

# ฟังก์ชันที่จำลองการทำงานที่ช้า
def spinner() -> None:
    with console.status("[bold green]Processing...", spinner="moon") as status:
        for _ in range(100):  # หมุนไปเรื่อยๆ
            time.sleep(0.1)

def main():
    console.print("Welcome to the CLI app!")
    spinner()  # เรียกใช้ฟังก์ชันที่มีวงกลมหมุน

if __name__ == "__main__":
    main()
