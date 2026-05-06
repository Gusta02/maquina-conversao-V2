from core.llm_engine import LLMEngine
import json

engine = LLMEngine()

# 1. Testar Fase 1 (Gerar Rascunho)
print("--- FASE 1: RASCUNHO ---")
rascunho = engine.generate_draft(
    theme="Os 3 segredos para dormir melhor",
    format_type="vertical",
    tone="informativo e direto",
    audience="adultos com insônia",
    duration_sec=60
)
print(f"\n{rascunho}\n")

# 2. Testar Fase 2 (Estruturar JSON)
print("--- FASE 2: ESTRUTURAÇÃO JSON ---")
json_estruturado = engine.structure_script(rascunho, "vertical")
print(json.dumps(json_estruturado, indent=2, ensure_ascii=False))