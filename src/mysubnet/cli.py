import typer
from typing import Annotated

from communex._common import get_node_url  # type: ignore
from communex.client import CommuneClient  # type: ignore
from communex.compat.key import classic_load_key  # type: ignore

from .validator._config import ValidatorSettings
from .validator.validator import GPUTaskValidator, get_subnet_netuid

app = typer.Typer()


@app.command("serve-subnet")
def serve(
    commune_key: Annotated[
        str, typer.Argument(help="Name of the key present in `~/.commune/key`")
    ],
):
    keypair = classic_load_key(commune_key)  # type: ignore
    settings = ValidatorSettings()  # type: ignore
    call_timeout=settings.call_timeout,
    c_client = CommuneClient(get_node_url(use_testnet=settings.use_testnet))
    subnet_uid = get_subnet_netuid(c_client, settings.subnet_name)
    validator = GPUTaskValidator(
        keypair,
        subnet_uid,
        c_client,
        call_timeout=call_timeout,
    )
    validator.validation_loop(settings)


if __name__ == "__main__":
    typer.run(serve)
