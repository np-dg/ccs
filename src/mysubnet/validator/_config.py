from pydantic_settings import BaseSettings


class ValidatorSettings(BaseSettings):
    # == Scoring ==
    iteration_interval: int = 800  # Set, accordingly to your tempo.
    max_allowed_weights: int = 400  # Query dynamically based on your subnet settings.
    subnet_name='ccs'
    use_testnet=True
    call_timeout=65
