from typing import ClassVar, Optional
from pathlib import Path
from rich_argparse import RichHelpFormatter
from pydantic_settings import (
    BaseSettings,
    CliSettingsSource,
    SettingsConfigDict,
    PydanticBaseSettingsSource,
    YamlConfigSettingsSource,
)


class BaseConfigWithYaml(BaseSettings):
    """
    This class extends Pydantic's BaseSettings to:
    - add support for loading configuration from a YAML file
    - change the precedence order as follows (highest to lowest):
        1. CLI arguments (via cli_parse_args)
        2. Instantiation arguments (init_settings)
        3. Environment variables (env_settings)
        4. Custom YAML config file (if provided)
        5. .env file (dotenv_settings)
        6. Default values (model defaults)

    Attributes:
        _yaml_file (ClassVar[Optional[Path]]): Class variable holding the path to the YAML configuration
            file. Must be set before instantiation. If set and the file exists, it will be used as a
            configuration source.

        model_config (SettingsConfigDict): Configuration dictionary specifying:
            - env_file: Path to .env file (".env")
            - env_prefix: Prefix for environment variables (empty string)
            - extra: How to handle extra attributes ("ignore")
            - cli_parse_args: Whether to parse command-line arguments (True, toggle per use case)
            
    Usage:
    ```python
    from pydantic import Field
    from pydantic_settings import SettingsConfigDict
    from ml_utils.base_config import BaseConfigWithYaml
    
    class MyConfig(BaseConfigWithYaml):
        param1: str = Field(..., description="Description for param1")
        param2: int = Field(42, description="Description for param2")
        
        model_config = SettingsConfigDict(
            env_prefix="MYAPP_",
            cli_parse_args=True,
        )
        
    # Set the YAML file path before instantiation
    BaseConfigWithYaml._yaml_file = Path("config.yaml")
    my_config = MyConfig()
    print(my_config.param1)
    ```

    """

    _yaml_file: ClassVar[Optional[Path]] = None  # set before instantiation

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources = [init_settings, env_settings]
        if cls._yaml_file and cls._yaml_file.exists():
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=cls._yaml_file))
        sources.append(dotenv_settings)
        cli = CliSettingsSource(
            settings_cls, formatter_class=RichHelpFormatter, cli_parse_args=True
        )
        return (cli, *sources)
