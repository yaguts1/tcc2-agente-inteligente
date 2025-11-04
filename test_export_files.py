"""Gera arquivos de teste (CSV e PDF) para verificação manual"""
from pathlib import Path
from ferramentas.exportador import ExportService, ExportFilters
from datetime import datetime, timedelta

# Configurar
db_path = Path('dados.db')
service = ExportService(str(db_path))
filters = ExportFilters()  # Sem filtros = exportar tudo

# Criar pasta de saída
output_dir = Path('relatorios')
output_dir.mkdir(exist_ok=True)

print("="*60)
print("GERANDO ARQUIVOS DE TESTE")
print("="*60)

# 1. CSV completo (todos os alertas)
print("\n1. Gerando CSV completo...")
csv_content = service.export_to_csv(filters)
csv_file = output_dir / f"alertas_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
with open(csv_file, 'w', encoding='utf-8') as f:
    f.write(csv_content)
print(f"   ✓ {csv_file}")
print(f"   ✓ Tamanho: {len(csv_content)} caracteres")

# 2. PDF completo
print("\n2. Gerando PDF completo...")
pdf_bytes = service.export_to_pdf(filters)
pdf_file = output_dir / f"alertas_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
with open(pdf_file, 'wb') as f:
    f.write(pdf_bytes)
print(f"   ✓ {pdf_file}")
print(f"   ✓ Tamanho: {len(pdf_bytes)} bytes")

# 3. CSV filtrado (apenas status 'fechado')
print("\n3. Gerando CSV filtrado (status='completed')...")
filters_completed = ExportFilters(status='completed')
csv_completed = service.export_to_csv(filters_completed)
csv_file_completed = output_dir / f"alertas_fechados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
with open(csv_file_completed, 'w', encoding='utf-8') as f:
    f.write(csv_completed)
print(f"   ✓ {csv_file_completed}")

# 4. PDF filtrado (últimas 24h)
print("\n4. Gerando PDF filtrado (últimas 24h)...")
filters_24h = ExportFilters(
    start_date=datetime.now() - timedelta(days=1),
    end_date=datetime.now()
)
pdf_24h = service.export_to_pdf(filters_24h)
pdf_file_24h = output_dir / f"alertas_24h_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
with open(pdf_file_24h, 'wb') as f:
    f.write(pdf_24h)
print(f"   ✓ {pdf_file_24h}")

print("\n" + "="*60)
print("ARQUIVOS GERADOS COM SUCESSO!")
print("="*60)
print(f"\nVerifique a pasta: {output_dir.absolute()}")
