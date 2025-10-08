"""Configuration du microservice de recherche."""
from pydantic_settings import BaseSettings
from typing import Dict


class Settings(BaseSettings):
    """Configuration de l'application."""

    # Meilisearch
    MEILISEARCH_URL: str = "http://localhost:7700"
    MEILISEARCH_API_KEY: str = ""

    # Limites
    DEFAULT_LIMIT: int = 1_000_000
    MAX_LEVENSHTEIN_DISTANCE: int = 4
    MIN_SCORE: float = 3.0

    # Scoring - Pénalités
    W_MISSING: float = 0.6
    W_FUZZY: float = 0.5
    W_RATIO: float = 1.0
    W_EXTRA_LENGTH: float = 0.15

    # Scoring - Bonus
    BONUS_MAX: float = 2.0
    BONUS_A_MISSING: float = 0.3
    BONUS_C_AVGDIST: float = 0.35
    BONUS_WORD_RATIO_MIN: float = 0.4
    BONUS_EXTRA_RATIO_MAX: float = 1.0

    # Seuils
    EXACT_THRESHOLD: float = 10.0
    EXACT_FULL_CAP: float = 9.99
    NO_SPACE_MIN_SCORE: float = 7.0



    # Priorités de type d'appariement
    TYPE_PRIORITY: Dict[str, int] = {
        'exact_full': 0,
        'exact_with_extras': 1,
        'no_space_match': 1,
        'near_perfect': 2,
        'phonetic_strict': 3,
        'exact_with_missing': 4,
        'fuzzy_full': 5,
        'hybrid': 6,
        'phonetic_tolerant': 7,
        'fuzzy_partial': 8,
        'partial': 9,
    }
    SYNONYMS_FR: Dict[str, list[str]] = {
            'saint' : ['st','st.'],
            'sainte' : ['ste','ste.'],
            'notre-dame' : ['n.d.','nd','notre dame'],
            'mont' : ['mt'],
            'grand' : ['gr','gd'],
            'petit' : ['pt','p\'tit'],

            'restaurant' : ['resto','restau','table','établissement'],
            'brasserie' : ['bistrot','bistro','taverne','estaminet'],
            'café' : ['bar','buvette','salon de thé','comptoir'],
            'auberge' : ['hostellerie','relais'],
            'crêperie' : ['creperie','galetterie'],
            'sandwicherie' : ['snack','sandwich'],
            'pizzeria' : ['pizza','italien'],
            'boulangerie' : ['boulanger','pain','patisserie'],


            'chinois' : ['asiatique','oriental','chine'],
            'japonais' : ['sushi','japon','nippon','ramen','yakitori'],
            'indien' : ['curry','inde','tandoor','bollywood'],
            'italien' : ['italie','pasta','pizzeria'],
            'français' : ['traditionnel','classique','terroir','hexagonal'],
            'américain' : ['burger','hamburger','fast-food','usa'],
            'mexicain' : ['tex-mex','mexique','tacos'],
            'libanais' : ['oriental','liban','mezze'],
            'grec' : ['grèce','hellénique','souvlaki'],
            'turc' : ['turquie','kebab','döner'],
            'thaï' : ['thaïlande','thai','pad-thai'],
            'vietnamien' : ['vietnam','pho','nem'],
            'marocain' : ['maroc','maghrébin','tajine','couscous'],


            'alsacien' : ['alsace','choucroute','bretzel'],
            'breton' : ['bretagne','crêpe','galette','cidre'],
            'provençal' : ['provence','méditerranéen','bouillabaisse'],
            'lyonnais' : ['lyon','bouchon','quenelle'],
            'normand' : ['normandie','calvados','camembert'],
            'savoyard' : ['savoie','fondue','raclette','tartiflette'],
            'auvergnat' : ['auvergne','truffade','cantal'],
            'gascon' : ['gascogne','cassoulet','confit'],


            'mcdonalds' : ['mcdonald\'s','mcdo','macdo','ronald','mcdonald','macdonalds','macdonald\'s','macdonald'],
            'kfc' : ['kentucky','poulet frit'],
            'quick' : ['burger king'],
            'subway' : ['sub','sandwich'],


            'livraison' : ['delivery','à domicile','emporter','takeaway'],
            'terrasse' : ['extérieur','dehors','jardin','patio'],
            'climatisé' : ['clim','air conditionné'],
            'parking' : ['stationnement','garage'],
            'wifi' : ['internet','connexion'],

            'romantique' : ['amoureux','intime','cosy'],
            'familial' : ['famille','enfants','kids'],
            'branché' : ['tendance','mode','hip'],
            'traditionnel' : ['authentique','ancien','classique'],
            'moderne' : ['contemporain','design'],


            'pas cher' : ['économique','abordable','bon marché'],
            'cher' : ['luxe','haut de gamme','gastronomique'],
            'menu' : ['formule','plat du jour'],


            'ouvert' : ['open'],
            'fermé' : ['closed'],
            'midi' : ['déjeuner','lunch'],
            'soir' : ['dîner','dinner'],


            'centre-ville' : ['centre','hypercentre','coeur de ville'],
            'gare' : ['station','terminus'],
            'aéroport' : ['airport','terminal'],
            'université' : ['fac','campus','étudiants'],
            'hôpital' : ['clinique','médical'],
            'zone commerciale' : ['centre commercial','galerie marchande'],


            'ritz' : ['le ritz','hotel ritz','palace ritz'],
            'plaza' : ['le plaza','plaza athénée'],
            'bristol' : ['le bristol','hotel bristol'],
            'george v' : ['george 5','four seasons george v'],
            'crillon' : ['le crillon','hotel de crillon'],
            'meurice' : ['le meurice','hotel meurice'],
            'shangri-la' : ['shangri la','hotel shangri-la'],

            'café de la paix' : ['de la paix','peace café'],
            'fouquet\'s' : ['fouquets','le fouquet\'s'],
            'angelina' : ['salon angelina','thé angelina'],
            'ladurée' : ['laduree','salon ladurée'],
            'berthillon' : ['glacier berthillon','ile saint louis'],

            'marché des enfants rouges' : ['enfants rouges','marché enfants rouges'],
            'marché saint germain' : ['st germain marché','marché st germain'],
            'marché aux puces' : ['puces','puces de saint-ouen'],
            'marché couvert' : ['halles','marché des halles'],

            'drive' : ['drive-in','au volant','sans descendre'],
            'click and collect' : ['click & collect','retrait magasin','à récupérer'],
            'brunch' : ['petit-déjeuner tardif','breakfast'],
            'afterwork' : ['after-work','après travail','5 à 7'],
            'happy hour' : ['heure heureuse','prix réduits'],


            'végétarien' : ['végé','veggie','sans viande'],
            'végan' : ['vegan','végétalien','plant-based'],
            'sans gluten' : ['gluten-free','intolérant gluten','coeliaque'],
            'halal' : ['musulman','certifié halal'],
            'casher' : ['kasher','cacher','juif','rabbinique'],
    }

    # Performance
    PARALLEL_STRATEGIES: bool = True
    ENABLE_METRICS: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
