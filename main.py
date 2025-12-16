"""
Pipeline Orquestrador - YouTube Shorts Automation
Executa todo o pipeline de forma integrada: download → transcribe → analyze → cut → export
"""

import sys
import time
import logging
import argparse
from pathlib import Path
from typing import Optional, Dict, List
from glob import glob
import re

# Importar funções dos scripts
sys.path.insert(0, str(Path(__file__).parent))

# Imports dinâmicos usando importlib (arquivos com números como prefixo)
def load_stage_module(stage: str):
    """
    Carrega módulo de uma etapa específica sob demanda.

    Args:
        stage: Nome da etapa (download, transcribe, analyze, cut, export)

    Returns:
        Módulo carregado
    """
    import importlib.util

    stage_map = {
        'download': '1_download.py',
        'transcribe': '2_transcribe.py',
        'analyze': '3_analyze.py',
        'cut': '4_cut.py',
        'export': '5_export.py'
    }

    script_name = stage_map[stage]
    scripts_dir = Path(__file__).parent / 'scripts'
    script_path = scripts_dir / script_name

    spec = importlib.util.spec_from_file_location(script_name, script_path)
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
        return module
    except ImportError as e:
        logger.error(f"Erro ao carregar módulo {script_name}: {e}")
        logger.error(f"Instale as dependências necessárias: pip install -r requirements.txt")
        raise

# Cache de módulos carregados
_loaded_modules = {}

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class PipelineRunner:
    """Orquestrador do pipeline de Shorts."""

    STAGES = ["download", "transcribe", "analyze", "cut", "export"]

    CHECKPOINTS = {
        "download": "data/raw/{video_id}.mp4",
        "transcribe": "data/transcripts/{video_id}_transcript.json",
        "analyze": "data/analysis/{video_id}_analysis.json",
        "cut": "data/output/{video_id}_cut_*.mp4",
        "export": "data/output/shorts/{video_id}_*_short.mp4"
    }

    def __init__(self, url: str, resume: bool = False, skip_stages: List[str] = None,
                 stop_on_error: bool = True, verbose: bool = False):
        """
        Inicializa o orquestrador.

        Args:
            url: URL do vídeo do YouTube
            resume: Continua do último checkpoint
            skip_stages: Lista de etapas para pular
            stop_on_error: Para no primeiro erro ou continua
            verbose: Logs detalhados
        """
        self.url = url
        self.video_id = self._extract_video_id(url)
        self.resume = resume
        self.skip_stages = skip_stages or []
        self.stop_on_error = stop_on_error
        self.verbose = verbose

        self.start_time = time.time()
        self.stage_times = {}
        self.results = {}

        if verbose:
            logger.setLevel(logging.DEBUG)

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extrai video_id da URL do YouTube."""
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'(?:embed\/)([0-9A-Za-z_-]{11})',
            r'^([0-9A-Za-z_-]{11})$'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def _check_stage_completed(self, stage: str) -> bool:
        """Verifica se uma etapa já foi concluída (checkpoint exists)."""
        if not self.video_id:
            return False

        pattern = self.CHECKPOINTS[stage].format(video_id=self.video_id)
        files = glob(pattern)
        completed = len(files) > 0

        if completed:
            logger.info(f"[{stage.upper()}] Checkpoint detectado - etapa já concluída")

        return completed

    def _should_skip_stage(self, stage: str) -> bool:
        """Determina se deve pular uma etapa."""
        # Pula se explicitamente solicitado
        if stage in self.skip_stages:
            logger.info(f"[{stage.upper()}] Pulando (--skip-{stage})")
            return True

        # Pula se modo resume e já concluída
        if self.resume and self._check_stage_completed(stage):
            return True

        return False

    def validate_dependencies(self) -> bool:
        """
        Valida dependências necessárias.

        Returns:
            True se todas as deps estão OK, False caso contrário
        """
        logger.info("=" * 60)
        logger.info("VALIDANDO DEPENDÊNCIAS")
        logger.info("=" * 60)

        try:
            import shutil
            import yaml
            from dotenv import load_dotenv

            # Ferramentas CLI
            tools = {
                'yt-dlp': 'Download de vídeos',
                'ffmpeg': 'Processamento de vídeo'
            }

            missing_tools = []
            for tool, description in tools.items():
                if shutil.which(tool):
                    logger.info(f"[OK] {tool} - {description}")
                else:
                    logger.error(f"[FALTA] {tool} - {description}")
                    missing_tools.append(tool)

            # Pacotes Python
            packages = {
                'yaml': ('pyyaml', True),
                'dotenv': ('python-dotenv', True),
                'anthropic': ('anthropic', False),
                'faster_whisper': ('faster-whisper', False)
            }

            missing_packages = []
            for import_name, (package_name, required) in packages.items():
                try:
                    __import__(import_name.replace('-', '_'))
                    logger.info(f"[OK] {package_name}")
                except ImportError:
                    level = logger.error if required else logger.warning
                    level(f"[FALTA] {package_name}")
                    if required:
                        missing_packages.append(package_name)

            # Verificar .env
            load_dotenv()
            import os
            if os.getenv('ANTHROPIC_API_KEY'):
                logger.info("[OK] ANTHROPIC_API_KEY configurada")
            else:
                logger.warning("[AVISO] ANTHROPIC_API_KEY não configurada (necessária para análise)")

            if missing_tools or missing_packages:
                logger.error("\n[ERRO] Dependências faltando!")
                if missing_tools:
                    logger.error(f"Ferramentas: {', '.join(missing_tools)}")
                if missing_packages:
                    logger.error(f"Pacotes: {', '.join(missing_packages)}")
                logger.error("\nExecute: python scripts/check_dependencies.py")
                return False

            logger.info("[SUCCESS] Todas as dependências obrigatórias estão instaladas\n")
            return True

        except Exception as e:
            logger.error(f"Erro na validação: {e}")
            return False

    def execute_stage(self, stage: str):
        """
        Executa uma etapa específica do pipeline.

        Args:
            stage: Nome da etapa a executar

        Raises:
            Exception: Se a etapa falhar e stop_on_error=True
        """
        global _loaded_modules

        logger.info("=" * 60)
        logger.info(f"ETAPA: {stage.upper()}")
        logger.info("=" * 60)

        stage_start = time.time()

        try:
            # Carregar módulo sob demanda
            if stage not in _loaded_modules:
                _loaded_modules[stage] = load_stage_module(stage)

            module = _loaded_modules[stage]

            if stage == "download":
                result = module.download_video(self.url)
                self.results['video_path'] = result
                # Atualizar video_id se não foi extraído da URL
                if not self.video_id:
                    self.video_id = result.stem

            elif stage == "transcribe":
                video_path = self.results.get('video_path') or module.find_latest_video()
                result = module.transcribe_video(video_path)
                self.results['transcript'] = result

            elif stage == "analyze":
                transcript_path = Path(self.results.get('transcript', {}).get('transcript_path', ''))
                if not transcript_path.exists():
                    transcript_path = module.find_latest_transcript()
                result = module.analyze_transcript(transcript_path)
                self.results['analysis'] = result

            elif stage == "cut":
                if 'analysis' in self.results:
                    analysis_path = Path(self.results['analysis']['transcript_path']).parent.parent / 'analysis' / f"{self.video_id}_analysis.json"
                    video_path = self.results.get('video_path') or Path(f"data/raw/{self.video_id}.mp4")
                else:
                    video_path, analysis_path = module.find_latest_analysis()

                result = module.cut_video(video_path, analysis_path)
                self.results['cuts'] = result

            elif stage == "export":
                result = module.batch_export()
                self.results['shorts'] = result

            stage_time = time.time() - stage_start
            self.stage_times[stage] = stage_time

            logger.info(f"[{stage.upper()}] Concluído em {self._format_time(stage_time)}\n")

        except Exception as e:
            logger.error(f"[{stage.upper()}] ERRO: {e}")

            if self.stop_on_error:
                raise
            else:
                logger.warning(f"[{stage.upper()}] Continuando apesar do erro...\n")

    def run(self):
        """Executa o pipeline completo."""
        logger.info("\n" + "=" * 60)
        logger.info("YOUTUBE SHORTS AUTOMATION - PIPELINE")
        logger.info("=" * 60)
        logger.info(f"URL: {self.url}")
        logger.info(f"Video ID: {self.video_id or 'A ser extraído'}")
        logger.info(f"Modo: {'Resume (continua do último checkpoint)' if self.resume else 'Completo'}")
        logger.info("=" * 60 + "\n")

        # Validar dependências
        if not self.validate_dependencies():
            logger.error("Pipeline abortado devido a dependências faltando")
            sys.exit(1)

        # Executar etapas
        for stage in self.STAGES:
            if self._should_skip_stage(stage):
                continue

            try:
                self.execute_stage(stage)
            except KeyboardInterrupt:
                logger.warning("\n[INTERROMPIDO] Pipeline cancelado pelo usuário")
                sys.exit(1)
            except Exception as e:
                logger.error(f"\n[ERRO FATAL] Pipeline interrompido na etapa '{stage}': {e}")
                sys.exit(1)

        # Relatório final
        self._print_report()

    def _format_time(self, seconds: float) -> str:
        """Formata tempo em string legível."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs:02d}s"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}h {mins:02d}m"

    def _print_report(self):
        """Imprime relatório final do pipeline."""
        total_time = time.time() - self.start_time

        logger.info("\n" + "=" * 60)
        logger.info(f"PIPELINE CONCLUÍDO - {self.video_id}")
        logger.info("=" * 60)
        logger.info(f"Tempo total: {self._format_time(total_time)}\n")

        logger.info("Etapas:")
        for stage in self.STAGES:
            if stage in self.stage_times:
                time_str = self._format_time(self.stage_times[stage])
                logger.info(f"  [OK] {stage.capitalize()}: {time_str}")
            elif self._should_skip_stage(stage):
                logger.info(f"  [SKIP] {stage.capitalize()}: Pulado")
            else:
                logger.info(f"  [-] {stage.capitalize()}: Não executado")

        # Detalhes dos Shorts gerados
        if 'analysis' in self.results and 'cuts' in self.results['analysis']:
            logger.info(f"\nShorts Gerados ({len(self.results['analysis']['cuts'])}):")

            for i, cut in enumerate(self.results['analysis']['cuts'], 1):
                logger.info(f"\n{i}. [{cut.get('content_type', 'unknown')}] Score: {cut.get('viral_score', 0):.1f}/10 ({cut.get('duration', 0):.0f}s)")

                # Arquivo
                short_file = Path(f"data/output/shorts/{self.video_id}_cut_{i:02d}_short.mp4")
                if short_file.exists():
                    size_mb = short_file.stat().st_size / (1024 * 1024)
                    logger.info(f"   {short_file} ({size_mb:.1f} MB)")

                # Metadados
                if cut.get('on_screen_text'):
                    logger.info(f"   Texto: {cut['on_screen_text']}")
                if cut.get('emotions'):
                    logger.info(f"   Emoções: {', '.join(cut['emotions'])}")

            avg_score = self.results['analysis']['stats'].get('avg_viral_score', 0)
            logger.info(f"\nScore viral médio: {avg_score:.2f}/10")

        logger.info("=" * 60 + "\n")


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description='Pipeline completo de automação de YouTube Shorts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python main.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  python main.py "URL" --resume
  python main.py "URL" --skip-download --skip-transcribe
  python main.py "URL" --verbose
        """
    )

    parser.add_argument('url', help='URL do vídeo do YouTube')
    parser.add_argument('--resume', action='store_true',
                        help='Continua do último checkpoint (pula etapas já concluídas)')
    parser.add_argument('--skip-download', action='store_true',
                        help='Pula etapa de download')
    parser.add_argument('--skip-transcribe', action='store_true',
                        help='Pula etapa de transcrição')
    parser.add_argument('--skip-analyze', action='store_true',
                        help='Pula etapa de análise')
    parser.add_argument('--skip-cut', action='store_true',
                        help='Pula etapa de corte')
    parser.add_argument('--skip-export', action='store_true',
                        help='Pula etapa de exportação')
    parser.add_argument('--stop-on-error', action='store_true', default=True,
                        help='Para no primeiro erro (padrão)')
    parser.add_argument('--continue-on-error', action='store_false', dest='stop_on_error',
                        help='Continua mesmo se uma etapa falhar')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Logs detalhados (modo debug)')

    args = parser.parse_args()

    # Montar lista de etapas para pular
    skip_stages = []
    if args.skip_download:
        skip_stages.append('download')
    if args.skip_transcribe:
        skip_stages.append('transcribe')
    if args.skip_analyze:
        skip_stages.append('analyze')
    if args.skip_cut:
        skip_stages.append('cut')
    if args.skip_export:
        skip_stages.append('export')

    # Criar e executar pipeline
    pipeline = PipelineRunner(
        url=args.url,
        resume=args.resume,
        skip_stages=skip_stages,
        stop_on_error=args.stop_on_error,
        verbose=args.verbose
    )

    pipeline.run()


if __name__ == "__main__":
    main()
