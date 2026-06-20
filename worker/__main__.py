import typer

from worker.scheduler import run

app = typer.Typer()


@app.command()
def main(
    host: str = typer.Option("0.0.0.0", help="Bind host for the healthcheck server"),
    port: int = typer.Option(8001, help="Bind port for the healthcheck server"),
):
    run(host=host, port=port)


if __name__ == "__main__":
    app()
