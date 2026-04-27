# Maxxki-Cobol: HLASM to COBOL Transpiler

Maxxki-Cobol is a sophisticated transpiler designed to convert IBM High-Level Assembler (HLASM) source code into maintainable COBOL. It leverages a modular, plugin-based architecture and optional Machine Learning (ML) assistance to handle the complexities of mainframe legacy code modernization.

## 🚀 Key Features

- **Hybrid Parsing Engine**: Combines structural PLY-based AST generation with regex-based fallbacks for high resilience against varying HLASM dialects.
- **Intelligent Register Mapping**: Automatically maps Assembler registers (R0-R15) to COBOL `WORKING-STORAGE` variables (e.g., `WS-R0` through `WS-R15`).
- **Control Flow Transformation**: 
    - Converts `BR 14` to `GOBACK`.
    - Translates conditional branches (`BE`, `BNE`, `BL`, etc.) into idiomatic COBOL `IF` statements by tracking comparison states.
- **Literal Handling**: Automated extraction and conversion of HLASM literals (e.g., `=F'42'`) into COBOL numeric constants.
- **Plugin-Based Architecture**: Easily extendable instruction handlers organized by category (Arithmetic, Boolean, Branch, Move, etc.).
- **ML-Assisted Conversion**: Optional integration with Hugging Face models (like `Salesforce/codet5p-770m`) for complex statement translation.
- **Detailed Reporting**: Generates a comprehensive conversion report and a JSON-based review file for every processed source.

## 🛠️ Installation

Ensure you have Python 3.8+ installed.

```bash
# Clone the repository
git clone https://maxxki.github.hlasm-to-cobol.git
cd cobol

# Install dependencies and the package in editable mode
pip install -e .
```

## 📖 Usage

### Command Line

You can run the transpiler directly using the provided script entry point:

```bash
maxxki-convert sample.asm
```

Alternatively, use the main entry point:

```bash
python main.py sample.asm
```

The tool will generate:
- `sample.cbl`: The converted COBOL source code.
- `sample.json`: A detailed conversion report for auditing and manual review.

### Running Tests

The project includes a comprehensive suite of integration tests covering comparison logic, branching, and arithmetic.

```bash
pytest
```

## ⚙️ Configuration

The system uses a flexible configuration manager that loads settings in the following order of precedence:
1. **Hard-coded defaults**
2. **JSON/YAML configuration file**
3. **Environment variables** (prefixed with `MAXXKI_`)

### Key Settings

| Environment Variable | Description | Default |
|----------------------|-------------|---------|
| `MAXXKI_LOG_LEVEL` | Logging verbosity (DEBUG, INFO, etc.) | `INFO` |
| `MAXXKI_ENABLE_ML` | Enable/Disable ML-assisted conversion | `True` |
| `MAXXKI_ML_MODEL_NAME`| Hugging Face model identifier | `Salesforce/codet5p-770m` |
| `MAXXKI_ML_DEVICE` | Device for ML (auto, cuda, cpu) | `auto` |
| `MAXXKI_COBOL_TARGET` | Target COBOL dialect | `COBOL-85` |

## 🏗️ Project Structure

- `core/`: The engine room. Contains the orchestrator, parser, service registry, and ML bridge.
- `plugins/instruction/`: Individual instruction handlers (Arithmetic, Branching, Load/Store, etc.).
- `scripts/`: Utility scripts, including `audit.py` for conversion quality checks.
- `tests/`: Integration and unit tests.

## 📈 Status & Roadmap

The project is currently in a stable development phase. Recent milestones include robust Register-Mapping and Branch-Optimisation. 

**Upcoming:**
- [ ] Interactive CLI mode for manual conflict resolution.
- [ ] Expanded support for complex opcodes (e.g., `BXH`, `MVN`).
- [ ] HTML export for conversion reports.

---
*Developed for mainframe modernization and legacy code analysis.*
