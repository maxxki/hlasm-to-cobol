import pytest
from core.types import ParsedStatement, StatementType
from plugins.instruction.compare import CompareHandler
from plugins.instruction.branch import BranchHandler

@pytest.mark.parametrize("mnemonic, cobol_op", [
    ("BE", "="), ("BZ", "="),
    ("BNE", "NOT ="), ("BNZ", "NOT ="),
    ("BL", "<"), ("BM", "<"),
    ("BH", ">"), ("BP", ">"),
    ("BNL", "NOT <"), ("BNM", "NOT <"),
    ("BNH", "NOT >"), ("BNP", "NOT >"),
])
def test_conditional_branches(ctx, mnemonic, cobol_op):
    compare_h = CompareHandler()
    branch_h = BranchHandler()
    
    # 1. COMPARE
    stmt_comp = ParsedStatement(
        raw_text="CR 1,2",
        operation="CR", 
        operands=["1", "2"], 
        statement_type=StatementType.ASSEMBLER_INSTRUCTION
    )
    compare_h.handle(stmt_comp, ctx)
    
    # 2. CONDITIONAL BRANCH
    stmt_branch = ParsedStatement(
        raw_text=f"{mnemonic} TARGET",
        operation=mnemonic, 
        operands=["TARGET"], 
        statement_type=StatementType.ASSEMBLER_INSTRUCTION
    )
    res = branch_h.handle(stmt_branch, ctx)
    
    assert f"IF WS-R1 {cobol_op} WS-R2" in res.converted_statement
    assert "GO TO TARGET" in res.converted_statement
    assert ctx.last_compare_result is None # State cleanup
