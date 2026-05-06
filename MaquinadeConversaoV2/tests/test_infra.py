from core.project_manager import ProjectManager
from core.drive_manager import DriveManager
from core.garbage_collector import GarbageCollector

# 1. Criar Projeto Local
pm = ProjectManager()
proj = pm.create_project("Vídeo de Teste", "vertical", "Cliente Teste")

# 2. Criar um arquivo fake para teste
fake_file = pm.get_project_path(proj['id'], "output") / "test.txt"
fake_file.write_text("Conteúdo de teste para o Drive")

# 3. Upload para o Drive (Substitua pelo ID de uma pasta sua no Drive)
dm = DriveManager()
# ID_DA_PASTA_TESTE = "COLE_AQUI_UM_ID_DE_PASTA_DO_SEU_DRIVE"
# file_id = dm.upload_file(str(fake_file), folder_id=ID_DA_PASTA_TESTE)

# 4. Limpeza
# gc = GarbageCollector()
# gc.cleanup_project(proj['id'], drive_confirmed=True)