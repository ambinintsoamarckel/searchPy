# Utilisation de l'image Python Alpine légère
FROM python:3.13.8-alpine

# Définition du répertoire de travail
WORKDIR /app

# Copie des dépendances pour un meilleur cache Docker
COPY requirements.txt ./

# Installation des dépendances système nécessaires pour la compilation (gcc, etc.)
# Exécution de l'installation des paquets Python (y compris psutil qui doit être compilé),
# puis suppression immédiate des outils de compilation (apk del) pour un nettoyage optimal.
RUN apk add --no-cache gcc python3-dev musl-dev linux-headers \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del gcc python3-dev musl-dev linux-headers

# Copie du reste du code de l'application
COPY . .

# Commande de démarrage du serveur Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
