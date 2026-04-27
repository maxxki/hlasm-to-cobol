import pytest
from core.types import ConversionContext
from core import (
    ServiceRegistry,
    HLASMParser,
    DataDivisionPlugin,
    DirectivePlugin,
    DummyMLConverter,
    ConfigurationManager
)
from plugins.instruction import InstructionPlugin

@pytest.fixture(autouse=True)
def setup_services():
    """Wire up the IoC container for all tests."""
    ConfigurationManager().load()
    ServiceRegistry.register("parser", HLASMParser())
    ServiceRegistry.register("plugins", [
        DirectivePlugin(),
        DataDivisionPlugin(),
        InstructionPlugin(),
    ])
    ServiceRegistry.register("ml_converter", DummyMLConverter())

@pytest.fixture
def ctx():
    return ConversionContext()
