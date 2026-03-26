import os
import sys
from contextlib import contextmanager
from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from ml_utils.base_config import BaseConfigWithYaml


# %% [markdown]
# # Test Config. Definitions
# %%


class FunConfig(BaseConfigWithYaml):
    first_name: str = Field("Sahil")
    last_name: str = Field("M")
    age: int = Field(37)
    hobbies: list[str] = Field(["dance", "cook"])

    model_config = SettingsConfigDict(env_prefix="FUN_", cli_parse_args=False)


class CliConfig(BaseConfigWithYaml):
    """Separate config with CLI parsing enabled for CLI priority tests."""

    first_name: str = Field("Sahil")
    age: int = Field(37)

    model_config = SettingsConfigDict(env_prefix="CLI_", cli_parse_args=True)


class AppConfig1(BaseConfigWithYaml):
    field1: str = Field("default1")
    field2: int = Field(10)

    model_config = SettingsConfigDict(env_prefix="APP1_")


class AppConfig2(BaseConfigWithYaml):
    field1: str = Field("default2")
    field2: int = Field(20)

    model_config = SettingsConfigDict(env_prefix="APP2_")


# %% [markdown]
# # Helpers
# %%

@contextmanager
def clean_environment(*env_prefixes: str):
    """
    Snapshot and restore os.environ and sys.argv.
    Yields a write_file() helper that tracks and auto-deletes created files.
    Also resets _yaml_file on all test config classes.
    """
    original_argv = sys.argv[:]
    original_environ = os.environ.copy()
    created_files: list[Path] = []
    config_classes = [FunConfig, CliConfig, AppConfig1, AppConfig2]

    def write_file(path: str, content: str) -> Path:
        p = Path(path)
        p.write_text(content)
        created_files.append(p)
        return p

    try:
        sys.argv = ["test"]
        for key in list(os.environ.keys()):
            if any(key.startswith(p) for p in env_prefixes):
                del os.environ[key]
        for cls in config_classes:
            cls._yaml_file = None
        yield write_file
    finally:
        sys.argv = original_argv
        os.environ.clear()
        os.environ.update(original_environ)
        for f in created_files:
            if f.exists():
                f.unlink()
        for cls in config_classes:
            cls._yaml_file = None


# %% [markdown]
# # Tests

# %% [markdown]
# ## CLI Priority Tests
# %%


class TestCLIPriority:
    def test_cli_overrides_instantiation(self):
        """Priority 1 > 2: CLI beats instantiation args."""
        with clean_environment("CLI_"):
            sys.argv = ["test", "--first_name", "CliName", "--age", "40"]
            config = CliConfig(first_name="InitName", age=25)
            assert config.first_name == "CliName"
            assert config.age == 40

    def test_cli_overrides_env(self):
        """Priority 1 > 3: CLI beats env vars."""
        with clean_environment("CLI_"):
            os.environ["CLI_FIRST_NAME"] = "EnvName"
            os.environ["CLI_AGE"] = "30"
            sys.argv = ["test", "--first_name", "CliName", "--age", "40"]
            config = CliConfig()  # pyright: ignore[reportCallIssue]
            assert config.first_name == "CliName"
            assert config.age == 40

    def test_cli_overrides_yaml(self):
        """Priority 1 > 4: CLI beats YAML."""
        with clean_environment("CLI_") as write:
            write("config.yaml", "first_name: YamlName\nage: 28\n")
            CliConfig._yaml_file = Path("config.yaml")
            sys.argv = ["test", "--first_name", "CliName", "--age", "40"]
            config = CliConfig()  # pyright: ignore[reportCallIssue]
            assert config.first_name == "CliName"
            assert config.age == 40

    def test_cli_overrides_dotenv(self):
        """Priority 1 > 5: CLI beats .env file."""
        with clean_environment("CLI_") as write:
            write(".env", "CLI_FIRST_NAME=DotenvName\nCLI_AGE=25\n")
            sys.argv = ["test", "--first_name", "CliName", "--age", "40"]
            config = CliConfig()  # pyright: ignore[reportCallIssue]
            assert config.first_name == "CliName"
            assert config.age == 40


# %% [markdown]
# ## Priority Level Tests (adjacent pairs, no CLI)
# %%


class TestAdjacentPriority:
    def test_instantiation_overrides_env(self):
        """Priority 2 > 3: Instantiation args beat env vars."""
        with clean_environment("FUN_"):
            os.environ["FUN_FIRST_NAME"] = "EnvName"
            os.environ["FUN_AGE"] = "30"
            config = FunConfig(first_name="InitName", age=25)  # pyright: ignore[reportCallIssue]
            assert config.first_name == "InitName"
            assert config.age == 25

    def test_env_overrides_yaml(self):
        """Priority 3 > 4: Env vars beat YAML."""
        with clean_environment("FUN_") as write:
            write("config.yaml", "first_name: YamlName\nage: 28\n")
            FunConfig._yaml_file = Path("config.yaml")
            os.environ["FUN_FIRST_NAME"] = "EnvName"
            os.environ["FUN_AGE"] = "35"
            config = FunConfig()  # pyright: ignore[reportCallIssue]
            assert config.first_name == "EnvName"
            assert config.age == 35

    def test_yaml_overrides_dotenv(self):
        """Priority 4 > 5: YAML beats .env file."""
        with clean_environment("FUN_") as write:
            write(".env", "FUN_FIRST_NAME=DotenvName\nFUN_AGE=25\n")
            write("config.yaml", "first_name: YamlName\nage: 28\n")
            FunConfig._yaml_file = Path("config.yaml")
            config = FunConfig()  # pyright: ignore[reportCallIssue]
            assert config.first_name == "YamlName"
            assert config.age == 28

    def test_dotenv_overrides_defaults(self):
        """Priority 5 > 6: .env beats default values."""
        with clean_environment("FUN_") as write:
            write(".env", "FUN_FIRST_NAME=DotenvName\nFUN_AGE=45\n")
            config = FunConfig()  # pyright: ignore[reportCallIssue]
            assert config.first_name == "DotenvName"
            assert config.age == 45

    def test_defaults_when_no_sources(self):
        """Priority 6: defaults used when nothing else is set."""
        with clean_environment("FUN_"):
            if Path(".env").exists():
                Path(".env").unlink()
            config = FunConfig()  # pyright: ignore[reportCallIssue]
            assert config.first_name == "Sahil"
            assert config.last_name == "M"
            assert config.age == 37
            assert config.hobbies == ["dance", "cook"]


# %% [markdown]
# ## Full Chain Tests
# %%


class TestFullPriorityChain:
    def test_all_levels_one_field_each(self):
        """
        Each field resolved from a different priority source:
            first_name  → .env      (priority 5)
            last_name   → YAML      (priority 4)
            age         → env var   (priority 3)
            hobbies     → default   (priority 6)
        """
        with clean_environment("FUN_") as write:
            write(".env", "FUN_FIRST_NAME=DotenvFirstName\n")
            write("config.yaml", "last_name: YamlLastName\n")
            FunConfig._yaml_file = Path("config.yaml")
            os.environ["FUN_AGE"] = "50"
            config = FunConfig()  # pyright: ignore[reportCallIssue]
            assert config.first_name == "DotenvFirstName"
            assert config.last_name == "YamlLastName"
            assert config.age == 50
            assert config.hobbies == ["dance", "cook"]

    def test_complete_chain_all_sources_active(self):
        """
        All sources active simultaneously — highest priority wins per field:
            first_name  → init      (priority 2)
            last_name   → env var   (priority 3)
            age         → YAML      (priority 4)
            hobbies     → default   (priority 6)
        """
        with clean_environment("FUN_") as write:
            write(".env", "FUN_FIRST_NAME=DotenvFirst\nFUN_LAST_NAME=DotenvLast\nFUN_AGE=20\n")
            write("config.yaml", "first_name: YamlFirst\nlast_name: YamlLast\nage: 25\n")
            FunConfig._yaml_file = Path("config.yaml")
            os.environ["FUN_FIRST_NAME"] = "EnvFirst"
            os.environ["FUN_LAST_NAME"] = "EnvLast"
            config = FunConfig(first_name="InitFirst")  # pyright: ignore[reportCallIssue]
            assert config.first_name == "InitFirst"  # init wins
            assert config.last_name == "EnvLast"  # env wins
            assert config.age == 25  # YAML wins over .env
            assert config.hobbies == ["dance", "cook"]  # default

    def test_cli_at_top_of_full_chain(self):
        """
        CLI sits above all other sources:
            first_name  → CLI       (priority 1)
            age         → init      (priority 2) — CLI only provides first_name
        """
        with clean_environment("CLI_") as write:
            write(".env", "CLI_FIRST_NAME=DotenvFirst\nCLI_AGE=20\n")
            write("config.yaml", "first_name: YamlFirst\nage: 25\n")
            CliConfig._yaml_file = Path("config.yaml")
            os.environ["CLI_FIRST_NAME"] = "EnvFirst"
            os.environ["CLI_AGE"] = "30"
            sys.argv = ["test", "--first_name", "CliFirst"]
            config = CliConfig(age=35)  # pyright: ignore[reportCallIssue]
            assert config.first_name == "CliFirst"  # CLI wins
            assert config.age == 35  # init wins (CLI didn't provide age)

    def test_partial_override(self):
        """Different fields won by different sources in same instantiation."""
        with clean_environment("FUN_") as write:
            write(".env", "FUN_FIRST_NAME=DotenvFirst\nFUN_LAST_NAME=DotenvLast\nFUN_AGE=20\n")
            write("config.yaml", "first_name: YamlFirst\nlast_name: YamlLast\n")
            FunConfig._yaml_file = Path("config.yaml")
            os.environ["FUN_LAST_NAME"] = "EnvLastName"
            config = FunConfig(age=35)  # pyright: ignore[reportCallIssue]
            assert config.first_name == "YamlFirst"  # YAML wins over .env
            assert config.last_name == "EnvLastName"  # env wins over YAML
            assert config.age == 35  # init wins


# %% [markdown]
# ## Edge Cases
# %%


class TestEdgeCases:
    def test_nonexistent_yaml_silently_ignored(self):
        """Nonexistent YAML path should not raise; falls back to lower sources."""
        with clean_environment("FUN_"):
            FunConfig._yaml_file = Path("nonexistent.yaml")
            config = FunConfig(first_name="InitName")  # pyright: ignore[reportCallIssue]
            assert config.first_name == "InitName"

    def test_yaml_list_field(self):
        """YAML correctly deserialises list fields."""
        with clean_environment("FUN_") as write:
            write(
                "config.yaml",
                "first_name: YamlName\nage: 28\nhobbies:\n  - reading\n  - swimming\n",
            )
            FunConfig._yaml_file = Path("config.yaml")
            config = FunConfig()  # pyright: ignore[reportCallIssue]
            assert config.hobbies == ["reading", "swimming"]

    def test_dotenv_without_yaml(self):
        """.env works correctly when no YAML is provided."""
        with clean_environment("FUN_") as write:
            write(".env", "FUN_FIRST_NAME=EnvfileName\nFUN_AGE=25\n")
            config = FunConfig()  # pyright: ignore[reportCallIssue]
            assert config.first_name == "EnvfileName"
            assert config.age == 25

    def test_yaml_file_none_uses_lower_sources(self):
        """When _yaml_file is None, env and .env still work normally."""
        with clean_environment("FUN_") as write:
            write(".env", "FUN_FIRST_NAME=DotenvName\n")
            os.environ["FUN_AGE"] = "99"
            config = FunConfig()  # pyright: ignore[reportCallIssue]
            assert config.first_name == "DotenvName"
            assert config.age == 99


# %% [markdown]
# ## Multi-Config Coexistence
# %%

class TestMultiConfigCoexistence:
    def test_separate_env_prefixes_dont_bleed(self):
        """Two config classes with different env prefixes resolve independently."""
        with clean_environment("APP1_", "APP2_"):
            os.environ["APP1_FIELD1"] = "val_for_app1"
            os.environ["APP1_FIELD2"] = "111"
            os.environ["APP2_FIELD1"] = "val_for_app2"
            os.environ["APP2_FIELD2"] = "222"
            c1 = AppConfig1()  # pyright: ignore[reportCallIssue]
            c2 = AppConfig2()  # pyright: ignore[reportCallIssue]
            assert c1.field1 == "val_for_app1"
            assert c1.field2 == 111
            assert c2.field1 == "val_for_app2"
            assert c2.field2 == 222

    def test_separate_yaml_files(self):
        """Each config class can use its own YAML file independently."""
        with clean_environment("APP1_", "APP2_") as write:
            write("app1.yaml", "field1: yaml1_val\nfield2: 333\n")
            write("app2.yaml", "field1: yaml2_val\nfield2: 444\n")
            AppConfig1._yaml_file = Path("app1.yaml")
            AppConfig2._yaml_file = Path("app2.yaml")
            c1 = AppConfig1()  # pyright: ignore[reportCallIssue]
            c2 = AppConfig2()  # pyright: ignore[reportCallIssue]
            assert c1.field1 == "yaml1_val"
            assert c1.field2 == 333
            assert c2.field1 == "yaml2_val"
            assert c2.field2 == 444

    def test_yaml_file_state_is_per_class(self):
        """Setting _yaml_file on one class does not affect another."""
        with clean_environment("APP1_", "APP2_") as write:
            write("app1.yaml", "field1: yaml1_val\n")
            AppConfig1._yaml_file = Path("app1.yaml")
            c1 = AppConfig1()  # pyright: ignore[reportCallIssue]
            c2 = AppConfig2()  # pyright: ignore[reportCallIssue]
            assert c1.field1 == "yaml1_val"
            assert c2.field1 == "default2"  # unaffected by AppConfig1's yaml

    def test_init_overrides_env_independently(self):
        """Init override for one config doesn't affect the other."""
        with clean_environment("APP1_", "APP2_"):
            os.environ["APP1_FIELD2"] = "999"
            os.environ["APP2_FIELD2"] = "888"
            c1 = AppConfig1(field2=555)  # pyright: ignore[reportCallIssue]
            c2 = AppConfig2(field2=666)  # pyright: ignore[reportCallIssue]
            assert c1.field2 == 555
            assert c2.field2 == 666
