import json
from typing import List, Dict, Any
from core.types import ConversionResult, ConversionReport

class ReportGenerator:
    """Generates structured JSON reports for conversion review."""
    
    @staticmethod
    def generate(report: ConversionReport) -> str:
        data = {
            "summary": {
                "source": report.source_path,
                "total_lines": report.total_lines,
                "success_rate": round(report.success_rate, 2),
                "high_risk_count": sum(1 for a in report.audit_trail if a.risk_level.value == "HIGH")
            },
            "details": []
        }
        
        for res in report.results:
            data["details"].append({
                "original": res.original_statement,
                "cobol": res.converted_statement,
                "risk": res.risk_level.value,
                "confidence": res.confidence.value,
                "plugin": res.plugin_name
            })
            
        return json.dumps(data, indent=2)
