# maxxki hlasm-to-cobol 🔧

> **M**A**X**X**K**I**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![COBOL-85](https://img.shields.io/badge/target-COBOL--85-green.svg)](https://www.ibm.com/docs/en/cobol-zos)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Dieses System ist ein intelligenter, plugin-basierter Konverter zur automatisierten Migration von IBM High Level Assembler (HLASM) nach COBOL-85. Das Framework kombiniert regelbasierte Transformation mit optionaler ML-gestützter Code-Generierung und symbolischer Zustandsanalyse.

---

## 🚀 Features

| Feature | Status | Beschreibung |
|---------|--------|--------------|
| **Rule-based Conversion** | ✅ Produktiv | 40+ HLASM-Opcode-Handler mit deterministischer COBOL-Ausgabe |
| **Plugin-Architektur** | ✅ Produktiv | Erweiterbares Handler-Chain-Pattern mit Prioritäts-Routing |
| **Hybrid Parser** | ✅ Produktiv | PLY-basierter Lexer mit Regex-Fallback für maximale Kompatibilität |
| **Symbolic Execution** | 🔄 Beta | Register-Tracking, Condition-Code-Analyse, Data-Flow-Erkennung |
| **ML-Fallback** | 🔄 Beta | HuggingFace CodeT5+ Integration für unbekannte Patterns |
| **Audit & Reporting** | ✅ Produktiv | Strukturierte JSON-Reports mit Konfidenz- und Risiko-Bewertung |
| **DSECT-to-Copybook** | 📋 Roadmap | Automatische COBOL COPY-Book-Generierung aus Assembler-DSECTs |
| **Semantic Watchdog** | 📋 Roadmap | Differential Testing via Hercules-Emulator zur Semantik-Verifikation |

---

## 📦 Installation

```bash
# Repository klonen
git clone https://github.com/dein-org/maxxki.git
cd maxxki

# Virtuelle Umgebung empfohlen
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Basis-Abhängigkeiten
pip install -r requirements.txt

# Optional: ML-Unterstützung (CodeT5+)
pip install transformers torch

# Optional: PLY-Parser (bessere Genauigkeit)
pip install ply
```

### Systemvoraussetzungen

- **Python 3.10+**
- **Linux/macOS/Windows** (WSL empfohlen für Hercules-Integration)
- **8 GB RAM** (16 GB mit ML-Backend)
- **Optional:** Hercules Emulator für Semantic Watchdog

---

## 🎯 Schnellstart

### Einzeldatei konvertieren

```bash
python -m maxxki convert examples/arith.asm --output arith.cbl
```

### Batch-Migration

```bash
python -m maxxki batch ./source-dir --output ./cobol-output/ --report migration.json
```

### Programmatische Nutzung

```python
from maxxki.core import Orchestrator, ServiceRegistry
from maxxki.core.config import ConfigurationManager

# Services initialisieren
ConfigurationManager().load()
setup_services()  # Parser, Plugins, ML-Bridge registrieren

# Konvertierung
orch = Orchestrator()
report = orch.convert_file("examples/arith.asm")

# Ergebnisse
print(f"Erfolgsrate: {report.success_rate * 100:.1f}%")
print(f"Dauer: {report.duration_ms:.2f} ms")
print(report.cobol_text)

# Report speichern
report.save_json("migration-report.json")
```

---

## 🏗️ Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                         maxxki                               │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │   Parser    │───→│ Orchestrator│───→│  Plugin-Chain   │  │
│  │ (PLY/Regex) │    │  (Pipeline) │    │  (Priority)     │  │
│  └─────────────┘    └──────┬──────┘    └─────────────────┘  │
│                            │                                 │
│              ┌─────────────┼─────────────┐                   │
│              ▼             ▼             ▼                   │
│  ┌─────────────────┐ ┌──────────┐ ┌─────────────────┐       │
│  │ DataDivisionPlugin│ │Instruction│ │  ML-Bridge      │       │
│  │ (DS/DC → COBOL) │ │Plugin    │ │ (CodeT5+)       │       │
│  └─────────────────┘ └────┬─────┘ └─────────────────┘       │
│                           │                                  │
│              ┌────────────┼────────────┐                    │
│              ▼            ▼            ▼                    │
│  ┌──────────────┐ ┌────────────┐ ┌──────────────┐          │
│  │ArithmeticHandler│ │BranchHandler│ │LoadStoreHandler│          │
│  │MoveHandler     │ │CompareHandler│ │BooleanHandler │          │
│  │ShiftHandler    │ │DecimalHandler│ │FallbackHandler│          │
│  └──────────────┘ └────────────┘ └──────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

### Plugin-Prioritäten

| Priorität | Plugin | Zweck |
|-----------|--------|-------|
| 1000 | `DirectivePlugin` | Strukturelle Direktiven (CSECT, END) |
| 900 | `DataDivisionPlugin` | Daten-Definitionen (DS, DC) |
| 500 | `InstructionPlugin` | Opcode-Routing zu Sub-Handlern |
| -1 | `ML-Fallback` | KI-gestützte Konvertierung |

---

## 📋 Unterstützte HLASM-Instruktionen

### Arithmetik
- **Add:** `A`, `AR`, `AH`, `AHI`, `AL`, `ALR`, `ALFI`
- **Subtract:** `S`, `SR`, `SH`, `SHI`, `SL`, `SLR`, `SLFI`
- **Multiply:** `M`, `MR`, `MH`, `MHI`, `MS`, `MSR`
- **Divide:** `D`, `DR`
- **Decimal:** `AP`, `SP`, `MP`, `DP`, `ZAP`, `CP`

### Datenbewegung
- **Load/Store:** `L`, `LR`, `LA`, `LH`, `ST`, `STM`, `LM`
- **Move:** `MVC`, `MVI`, `MVCL`, `MVN`, `MVZ`, `MVCIN`
- **Conversion:** `PACK`, `UNPK`, `CVB`, `CVD`

### Verzweigung
- **Unconditional:** `B`, `BR`, `BAL`, `BALR`, `BAS`, `BASR`
- **Conditional:** `BC`, `BCR`, `BE`, `BNE`, `BH`, `BL`, `BZ`, `BNZ`
- **Loop:** `BCT`, `BCTR`, `BXH`, `BXLE`

### Logik & Vergleich
- **Boolean:** `N`, `NR`, `NC`, `NI`, `O`, `OR`, `OC`, `OI`, `X`, `XR`, `XC`, `XI`
- **Compare:** `CR`, `CLR`, `C`, `CL`, `CH`, `CLC`, `TM`, `TMH`, `TML`
- **Shift:** `SLL`, `SRL`, `SLA`, `SRA`, `SLDL`, `SRDL`, `SLDA`, `SRDA`

> **Hinweis:** Vollständige Opcode-Matrix siehe [`docs/opcodes.md`](docs/opcodes.md)

---

## 📊 Konfidenz- & Risiko-Modell

Jede Konvertierung wird mit **Konfidenz** und **Risiko** bewertet:

```python
class ConversionConfidence(Enum):
    HIGH    = "Deterministisch, regelbasiert"
    MEDIUM  = "Heuristisch, manuelle Prüfung empfohlen"
    LOW     = "ML-generiert, Review erforderlich"
    UNKNOWN = "Nicht konvertiert, TODO-Stub"

class RiskLevel(Enum):
    NONE     = "Kein Risiko"
    LOW      = "Kosmetische Anpassungen möglich"
    MEDIUM   = "Logik-Prüfung empfohlen"
    HIGH     = "Manuelle Nachbearbeitung erforderlich"
    CRITICAL = "Semantische Divergenz erkannt"
```

---

## 🔧 Konfiguration

### Via `maxxki.json`

```json
{
  "cobol_target": "COBOL-85",
  "generate_copybooks": true,
  "preserve_comments": true,
  "enable_ml": true,
  "ml_model_name": "Salesforce/codet5p-770m",
  "ml_quantization": 8,
  "min_ml_confidence": 0.30,
  "log_level": "INFO"
}
```

### Via Umgebungsvariablen

```bash
export MAXXKI_ENABLE_ML=true
export MAXXKI_ML_QUANTIZATION=4
export MAXXKI_COBOL_TARGET="COBOL-2002"
```

---

## 🧪 Testing

```bash
# Unit-Tests
pytest tests/unit -v

# Integrationstests mit Golden Masters
pytest tests/integration -v --golden-dir=tests/fixtures/

# Coverage
pytest --cov=maxxki --cov-report=html

# Semantische Verifikation (erfordert Hercules)
pytest tests/semantic -v --hercules-config=tests/hercules.cnf
```

---

## 📈 Roadmap

| Quartal | Meilenstein |
|---------|-------------|
| **Q2 2026** | Stabilisierung P0, Unit-Test-Abdeckung 80% |
| **Q3 2026** | DSECT-to-Copybook, Symbolic Execution v1 |
| **Q4 2026** | Semantic Watchdog (Hercules-Integration) |
| **Q1 2027** | Call-Graph-Visualizer, Batch-Parallelisierung |
| **Q2 2027** | Compliance-Plugin (PII-Erkennung) |
| **Q3 2027** | Agentic Feedback Loop (Human-in-the-Loop) |
| **Q4 2027** | Performance-Profiler, COBOL-Optimierung |

---

## 🤝 Mitwirken

Wir freuen uns über Beiträge! Siehe [`CONTRIBUTING.md`](CONTRIBUTING.md) für Details.

```bash
# Development-Setup
git clone https://github.com/dein-org/maxxki.git
cd maxxki
pip install -e ".[dev]"
pre-commit install
```

### Code of Conduct

Dieses Projekt folgt dem [Contributor Covenant](https://www.contributor-covenant.org/).

---

## 📄 Lizenz

**MIT License** – siehe [`LICENSE`](LICENSE)

```
Copyright (c) 2026 maxxki Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

## 🙏 Danksagung

- [PLY](https://www.dabeaz-course.com/practical-python/) – Python Lex-Yacc
- [HuggingFace Transformers](https://huggingface.co/docs/transformers) – CodeT5+ Modell
- [Hercules Emulator](http://www.hercules-390.org/) – IBM Z-System Emulation
- [IBM HLASM Language Reference](https://www.ibm.com/docs/en/zos/2.5.0?topic=reference-high-level-assembler-language) – Offizielle Dokumentation

---

> **⚠️ Haftungsausschluss:** maxxki ist ein Assistenzwerkzeug. Generierter COBOL-Code erfordert immer menschliche Review vor Produktivbetrieb. Die semantische Äquivalenz von Assembler und COBOL kann nicht in allen Fällen maschinell garantiert werden.

---

<p align="center">
  <strong>Made with 💙 for the Mainframe Community</strong><br>
  <a href="https://github.com/dein-org/maxxki/issues">Issues</a> •
  <a href="https://github.com/dein-org/maxxki/discussions">Discussions</a> •
  <a href="https://maxxki.readthedocs.io">Dokumentation</a>
</p>
