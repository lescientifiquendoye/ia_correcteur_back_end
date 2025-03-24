import re
import logging
import pdfplumber
import ollama
import chardet
import os
from pathlib import Path
from django.core.files.storage import default_storage
from django.utils.timezone import now
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

modeles= ["deepseek-r1:1.5b","deepseek-r1"]

def clean_response(content: str) -> str:
    """
    Nettoie la réponse de l'IA des balises et espaces superflus.
    
    Args:
        content (str): Contenu brut de la réponse
        
    Returns:
        str: Contenu nettoyé
    """
    if not content:
        return ""
    
    # Supprime le contenu entre les balises <think> et </think>
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    # Supprime les balises HTML restantes
    content = re.sub(r"<.*?>", "", content)
    # Remplace les espaces multiples et normalise
    content = re.sub(r"\s+", " ", content)
    # Supprime les espaces en début et fin
    return content.strip()

def extract_text(file_path: Path, file_format: str) -> str:
    """
    Extrait le texte d'un fichier PDF, Texte ou LaTeX avec une gestion améliorée.
    
    Args:
        file_path (Path): Chemin vers le fichier à extraire
        file_format (str): Format du fichier ('pdf', 'text', 'latex')
        
    Returns:
        str: Texte extrait du fichier
    """
    if not os.path.exists(file_path):
        logger.error(f"Le fichier n'existe pas: {file_path}")
        return ""
    
    try:
        if file_format.lower() == "pdf":
            return extract_from_pdf(file_path)
        elif file_format.lower() == "latex":
            return extract_from_latex(file_path)
        else:  # texte ou autre format texte
            return extract_from_text(file_path)
    except Exception as e:
        logger.error(f"Erreur lors de l'extraction du fichier ({file_format}): {e}")
        return ""

def extract_from_pdf(file_path: Path) -> str:
    """
    Extrait le texte d'un fichier PDF avec des optimisations pour les formats d'évaluation.
    """
    try:
        with pdfplumber.open(file_path) as pdf:
            text_content = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    # Préservation des numéros de questions et de leur formatting
                    page_text = re.sub(r'(\d+[\)\.-]\s)', r'\n\1', page_text)
                    # Préservation des questions à points (n pts)
                    page_text = re.sub(r'\((\d+)\s?(?:point|pt)s?\)', r'(\1 pts)', page_text, flags=re.IGNORECASE)
                    text_content.append(page_text)
            
            full_text = "\n".join(text_content)
            
            # Nettoyage final pour les questions d'évaluation
            full_text = re.sub(r'\n{3,}', '\n\n', full_text)  # Limit blank lines
            
            return full_text
    except Exception as e:
        logger.error(f"Erreur spécifique à l'extraction PDF: {e}")
        raise

def extract_from_latex(file_path: Path) -> str:
    """
    Extrait le texte d'un fichier LaTeX en préservant la structure des questions.
    """
    try:
        # Détection de l'encodage
        with open(file_path, 'rb') as raw_file:
            result = chardet.detect(raw_file.read())
            encoding = result['encoding'] if result['confidence'] > 0.7 else 'utf-8'
        
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            content = f.read()
            
            # Préserver les environnements de questions/exercices
            content = re.sub(r'\\begin\{(question|exercise|exercice)\}', r'\n\n', content, flags=re.IGNORECASE)
            content = re.sub(r'\\end\{(question|exercise|exercice)\}', r'\n\n', content, flags=re.IGNORECASE)
            
            # Préserver les numéros de questions
            content = re.sub(r'\\item', r'\n', content)
            
            # Supprimer les commentaires
            content = re.sub(r'%.*$', '', content, flags=re.MULTILINE)
            
            # Supprimer les commandes LaTeX courantes mais préserver le texte
            content = re.sub(r'\\(section|subsection|paragraph)\{(.*?)\}', r'\n\n\2\n', content)
            content = re.sub(r'\\[a-zA-Z]+(\[.*?\])?(?=\{)', '', content)
            content = re.sub(r'\{|\}', '', content)
            
            # Nettoyer les espaces excessifs tout en préservant la structure
            content = re.sub(r'\n{3,}', '\n\n', content)
            
            return content.strip()
    except Exception as e:
        logger.error(f"Erreur spécifique à l'extraction LaTeX: {e}")
        raise

def extract_from_text(file_path: Path) -> str:
    """
    Extrait le texte d'un fichier texte avec détection d'encodage.
    """
    try:
        # Détection automatique de l'encodage
        with open(file_path, 'rb') as raw_file:
            result = chardet.detect(raw_file.read())
            encoding = result['encoding'] if result['confidence'] > 0.7 else 'utf-8'
            
        # Lecture avec l'encodage détecté
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            content = f.read()
            # Normaliser les fins de lignes
            content = re.sub(r'\r\n', '\n', content)
            return content
    except Exception as e:
        logger.error(f"Erreur spécifique à l'extraction texte: {e}")
        raise

#@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def ask_deepseek(question: str) -> str:
    """
    Interroge DeepSeek pour obtenir une réponse concise en français avec système de retry.
    
    Args:
        question (str): La question ou consigne à traiter
        
    Returns:
        str: Réponse de l'IA
    """
    try:
        context = """Vous êtes un assistant spécialisé dans la correction d'examens et d'évaluations académiques.
        Voici les règles à suivre:
        1. Répondez toujours en français, de manière claire, précise et concise
        2. Structurez votre réponse pour faciliter la comparaison ultérieure avec les réponses des étudiants
        3. Incluez du code si la question le nécessite, en respectant les conventions syntaxiques
        4. Ne fournissez pas d'explications sur votre réponse - donnez uniquement le contenu attendu
        5. Adaptez votre niveau de détail à celui suggéré par la question"""
        
        response = ollama.chat(
            model=modeles[0],
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": question}
            ]
        )
        
        return clean_response(response["message"]["content"])
    except Exception as e:
        logger.error(f"Erreur lors de l'appel à l'IA (DeepSeek): {e}")
        raise

#@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))

def evaluate_student_answer(student_answer: str, ia_answer: str) -> float:
    """
    Évalue la réponse d'un étudiant par rapport à la réponse modèle avec system de retry.
    
    Args:
        student_answer (str): Réponse fournie par l'étudiant
        ia_answer (str): Réponse modèle générée par l'IA
        
    Returns:
        float: Score entre 0 et 1 représentant la qualité de la réponse
    """
    if not student_answer or not student_answer.strip():
        logger.warning("Réponse étudiant vide - attribution de la note 0")
        return 0.0
        
    if not ia_answer or not ia_answer.strip():
        logger.warning("Réponse modèle vide - attribution de la note par défaut 0.5")
        return 0.5
    
    try:
        context = """Vous êtes un professeur qui évalue les réponses des élèves selon ces critères stricts:
        1. Répondez UNIQUEMENT par un nombre décimal entre 0 et 1 (ex: 0.75)
        2. Évaluez la compréhension conceptuelle, pas la formulation exacte
        3. Donnez 0 pour une réponse complètement fausse ou hors sujet
        4. Donnez 0.5 pour une réponse partiellement correcte
        5. Donnez 1 pour une réponse complète et correcte
        6. Pour les valeurs intermédiaires, soyez précis (0.25, 0.6, 0.85, etc.)
        7. Soyez cohérent dans votre notation
        8. Ne fournissez aucun commentaire, explication ou justification
        9. Si le code est demandé, vérifiez sa logique et son exactitude"""
                 
        response = ollama.chat(
            model=modeles[0],
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": f"Modèle: {ia_answer}\n\nRéponse de l'élève: {student_answer}\n\nNotez la réponse entre 0 et 1 uniquement."}
            ]
        )
                 
        score_text = clean_response(response["message"]["content"])
        
        # Pattern pour extraire uniquement le nombre décimal ou entier
        score_match = re.search(r"^(?:note\s*[:=]\s*)?(\d+(?:\.\d+)?)(?:/\d+)?$", score_text, re.IGNORECASE)
        
        if score_match:
            # Si on trouve un pattern score/total, extraire juste le score
            score = float(score_match.group(1))
            return min(max(score, 0), 1)  # Garantir que la note est entre 0 et 1
        
        # Fallback pattern: chercher n'importe quel nombre dans la réponse
        score_match = re.search(r"(\d+(?:\.\d+)?)", score_text)
        if score_match:
            score = float(score_match.group(1))
            return min(max(score, 0), 1)  # Garantir que la note est entre 0 et 1
            
        logger.warning(f"Format de note non reconnu, utilisation de la valeur par défaut: '{score_text}'")
        return 0.5  # Valeur par défaut en cas d'erreur
    except Exception as e:
        logger.error(f"Erreur d'évaluation: {e}")
        return 0.5  # Valeur par défaut en cas d'erreur