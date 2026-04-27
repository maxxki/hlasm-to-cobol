import json
from pathlib import Path
from core import (
    ServiceRegistry,
    HLASMParser,
    DataDivisionPlugin,
    DirectivePlugin,
    DummyMLConverter,
    ConfigurationManager,
    Orchestrator
)
from plugins.instruction import InstructionPlugin
from core.types import RiskLevel

def setup_services():
    ConfigurationManager().load()
    ServiceRegistry.register("parser", HLASMParser())
    ServiceRegistry.register("plugins", [
        DirectivePlugin(),
        DataDivisionPlugin(),
        InstructionPlugin(),
    ])
    ServiceRegistry.register("ml_converter", DummyMLConverter())

def run_audit(target_dir: str):
    setup_services()
    orc = Orchestrator()
    summary = {"total_files": 0, "total_stmts": 0, "todos": 0, "high_risk": 0, "opcode_failures": {}}
    
    files = list(Path(target_dir).glob("*.asm"))
    for f in files:
        report = orc.convert_file(f)
        summary["total_files"] += 1
        summary["total_stmts"] += report.total_lines
        
        for res in report.results:
            if "TODO" in res.converted_statement:
                summary["todos"] += 1
                op = res.source.operation if res.source and res.source.operation else "UNKNOWN"
                summary["opcode_failures"][op] = summary["opcode_failures"].get(op, 0) + 1
            if res.risk_level == RiskLevel.HIGH:
                summary["high_risk"] += 1
                
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    run_audit("./")
