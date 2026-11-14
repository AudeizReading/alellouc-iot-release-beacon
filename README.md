# Release Beacon

Release Beacon est l'application web de la partie P3/Bonus du projet
**Inception of Things** de l'école 42. Elle sert de charge applicative
déployée dans Kubernetes et pilotée par Argo CD. L'application expose son
nom, sa version et le nom du Pod en HTML ou en JSON, afin de vérifier le
contenu réellement exécuté dans le cluster.

Le dépôt peut être utilisé de deux façons :

1. comme répertoire `release-beacon/` du dépôt parent
   `alellouc-iot` ;
2. comme dépôt autonome produit par `git subtree split`.

Le code applicatif et les fichiers de construction sont dans ce répertoire :

```text
release-beacon/
├── app/
│   ├── appli/
│   │   ├── css/stylesheet.css
│   │   └── index.html
│   ├── pyproject.toml
│   └── server/
├── .dockerignore
├── Dockerfile
└── img/release/digest/
    └── release-beacon-v1.release.yaml
```

Le fichier `img/release/digest/release-beacon-v1.release.yaml` contient le
digest de l'image Docker publiée. Il ne remplace pas le manifeste Kubernetes surveillé par
Argo CD ; il sert à conserver la référence exacte de l'image construite.

## Prérequis

### Utilisation autonome

Les outils suivants sont nécessaires :

- Git ;
- Docker ;
- Python 3.14 pour l'exécution locale hors conteneur ;
- `curl` pour les vérifications HTTP.

Le conteneur utilise l'image `python:3.14-slim` et installe les dépendances
déclarées dans [`app/pyproject.toml`](app/pyproject.toml) avec `uv`.

L'application attend qu'on lui fournisse les variables d'environnement suivantes (avec la valeur qui nous conviendra):

```bash
PART=<la-partie-du-sujet-iot-traitée>
APP_NAME=<nom-de-l-application>
PORT=<port-de-contact>
IOT_LEADER_LOGIN=<nom-du-leader-de-la-team-projet>
MAINTENER_MAIL=<mail-du-mainteneur-du-projet>

# Ce qui pourrait donner
PART=p3
APP_NAME=release-beacon
PORT=8887
IOT_LEADER_LOGIN=alellouc
MAINTENER_MAIL=alellouc@student.42nice.fr
```

#### v1

#### v2

### Utilisation depuis `alellouc-iot`

Le dépôt parent fournit en plus :

- `mise` pour sélectionner les variables et les outils du projet ;
- `ansible` et les playbooks d'infrastructure ;
- le profil P3 de [`.config/mise.p3.toml`](../.config/mise.p3.toml).

Le sujet de la partie P3 est conservé dans
[`docs/subject/en.subject.pdf`](../docs/subject/en.subject.pdf) du dépôt
[parent](https://gitlab.com/AudeizReading/alellouc-iot/-/tree/develop?ref_type=heads).
:warning: _Ce lien n'est disponible que lorsque le répertoire est utilisé dans
le monorepo._

## Démarrer depuis le dépôt autonome

Depuis la racine du dépôt `release-beacon` :

```bash
docker build \
  --tag audeizreading/release-beacon:v1 \
  --file Dockerfile \
  .
```

Le contexte Docker est `.`. Le `Dockerfile` copie `app/` dans `/app`, installe
les dépendances puis démarre `server.app`.

Lancer le conteneur :

```bash
docker run --rm \
  --publish 127.0.0.1:8080:8080 \
  --env APP_NAME=release-beacon \
  --env PART=p3 \
  --env PORT=8080 \
  --env IOT_LEADER_LOGIN='<login>' \
  --env MAINTENER_MAIL='<email>' \
  audeizreading/release-beacon:v1
```

Vérifier la réponse HTML :

```bash
curl --fail http://127.0.0.1:8080/
```

Vérifier la réponse JSON :

```bash
curl --fail \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/
```

La réponse JSON doit contenir au minimum les clés `app`, `pod` et `version`.
La valeur de `version` provient de `app/pyproject.toml`, et non du tag Docker
ou d'une variable d'environnement ajoutée au démarrage.

Le port, le nom de l'application et les autres variables sont chargés par
[`server/config/settings.py`](app/server/config/settings.py). Le rendu HTML,
le CSS et le favicon généré sont centralisés dans
[`server/response/page.py`](app/server/response/page.py).

## Construire depuis le dépôt parent

Depuis la racine de `alellouc-iot`, le contexte Docker doit rester
`release-beacon/` :

```bash
mise run play docker docker-image \
  docker_images_build_name=release-beacon \
  docker_images_build_tag=v1 \
  docker_images_build_state=present \
  docker_images_build_context=release-beacon/ \
  docker_images_build_dockerfile=release-beacon/Dockerfile \
  docker_images_build_push=true
```

Cette tâche est mutante : elle construit l'image et, avec
`docker_images_build_push=true`, la publie sur la registry configurée par le
playbook. La publication nécessite une authentification Docker appropriée.

Le playbook écrit ensuite le digest de l'image dans le fichier de release
prévu par le flux du projet. Ce fichier doit être conservé avec le commit qui
référence l'image correspondante. Le déploiement P3 utilise ensuite le
manifeste GitOps surveillé par Argo CD ; voir
[`docs/tech/10.p3-gitops.md`](../docs/tech/10.p3-gitops.md).

## Fonctionnement de `git subtree`

`git subtree` permet d'extraire un sous-répertoire d'un dépôt existant dans
une branche qui contient uniquement ce préfixe. L'extraction conserve
l'historique des commits qui ont modifié ce sous-répertoire, mais ne déplace
pas les fichiers et ne modifie pas la branche courante.

Dans le dépôt parent, l'opération est :

```text
historique de alellouc-iot
        │
        └── release-beacon/
                │
                └── git subtree split
                        │
                        └── branche exportée : release-beacon-export
```

La branche exportée a la racine du sous-répertoire. Un fichier
`release-beacon/Dockerfile` devient donc `Dockerfile` dans le dépôt exporté.

### Créer ou actualiser la branche exportée

Depuis la racine de `alellouc-iot` :

```bash
git subtree split \
  --prefix=release-beacon \
  --branch=release-beacon-export
```

La branche `release-beacon-export` est locale. La commande ne publie rien et
ne supprime rien du dépôt parent.

Le résultat peut être inspecté avant publication :

```bash
git ls-tree -r --name-only release-beacon-export
git log --oneline --decorate release-beacon-export
```

Le premier chemin doit être `README.md`, `Dockerfile` ou `app/...`, et non
`release-beacon/...`, car le préfixe a été retiré.

### Publier vers un remote différent du dépôt parent

Le dépôt parent utilise `origin` pour son remote GitLab. Le dépôt GitHub
Release Beacon est référencé séparément par le remote `rb-app` :

```bash
git remote -v
```

Si ce remote n'existe pas dans un clone neuf :

```bash
git remote add rb-app \
  git@github.com:AudeizReading/alellouc-iot-release-beacon.git
```

Publier l'export sur la branche `main` du dépôt GitHub :

```bash
git push rb-app release-beacon-export:main
```

Cette commande publie la branche exportée vers un remote différent sans
modifier `origin`. Elle ne fusionne pas automatiquement les commits propres
au dépôt distant. Si `main` contient déjà des commits indépendants, publier
directement peut être refusé ou nécessiter une intégration explicite.

Pour examiner le dépôt distant avant toute opération :

```bash
git fetch rb-app
git log --oneline --decorate --graph rb-app/main release-beacon-export
```

Une branche distante existante ne doit pas être écrasée avec `--force` sans
vérifier son contenu et obtenir l'autorisation des personnes qui la
maintiennent.

Si `rb-app/main` contient déjà un historique indépendant, publier d'abord
l'export sur une branche temporaire :

```bash
git push rb-app release-beacon-export:subtree-import
git fetch rb-app
git switch --create release-beacon-integration rb-app/main
git merge --allow-unrelated-histories \
  rb-app/subtree-import \
  --message "Import release-beacon subtree"
```

Les conflits doivent être résolus puis vérifiés avant publication :

```bash
git status
git add <fichiers-résolus>
git commit
git push rb-app release-beacon-integration:main
```

Cette intégration conserve l'historique déjà présent sur `main` et ajoute
l'historique issu du parent. La branche temporaire peut être supprimée après
validation si elle n'est plus nécessaire :

```bash
git push rb-app --delete subtree-import
```

### Récupérer les modifications GitHub dans le parent

Cette procédure concerne le subtree `release-beacon/`, tant que le dossier
reste suivi par le dépôt parent. Une PR fusionnée sur le `main` du dépôt
applicatif peut être réintégrée dans ce dossier depuis le remote `rb-app`.
Une PR encore ouverte n'est pas incluse dans `main`.

Exécuter les commandes depuis la racine de `alellouc-iot`, dans Bash ou Zsh.
La branche parent courante recevra la fusion ; vérifier sa sélection et son
état avant de commencer :

```bash
git branch --show-current
git status --short
```

#### Mettre le travail local à l'abri

Les opérations subtree qui fusionnent un historique exigent un arbre de
travail propre. Des modifications hors de `release-beacon/`, par exemple
dans les rôles Ansible, peuvent provoquer
`fatal: working tree has modifications.  Cannot add.`. Une simple mise en
index avec `git add` ne suffit pas.

Si des modifications doivent rester en attente, les sauvegarder avant
l'import. Exécuter ce bloc uniquement si le dépôt contient effectivement du
travail à mettre en réserve :

```bash
git stash push --include-untracked -m "before subtree release-beacon" &&
subtree_stash=$(git rev-parse --verify refs/stash) &&
git status --short
```

Le stash sauvegarde et retire temporairement les modifications et les
fichiers non suivis, hors fichiers ignorés. La variable `subtree_stash`
conserve l'identifiant de cette sauvegarde sans dépendre du rang des anciens
stashes. Garder le même terminal pour la restauration. Si la sauvegarde
échoue, arrêter la procédure. La sortie finale de `git status --short` doit
être vide avant de poursuivre.

Les changements destinés à faire partie d'un export subtree doivent être
commités : le stash protège du travail local, mais ne l'inclut pas dans
l'historique exporté.

#### Relier l'historique lors de la première récupération

Si le dossier a seulement été exporté par `git subtree split`, sans
rattachement préalable, relier cet historique au parent une première fois.
Un rattachement existant peut être repéré avec :

```bash
git log --format='%h %s' --grep='^git-subtree-dir: release-beacon$' -1
```

Lorsque ce rattachement manque après un export par split :

```bash
git subtree split --prefix=release-beacon --rejoin
```

`--rejoin` crée le commit de rattachement dans la branche parent courante.
Cette étape ne publie rien et ne remplace pas les fichiers du dossier.
Lorsqu'un rattachement existe déjà, passer directement à la récupération.

#### Importer puis restaurer le travail local

```bash
git subtree pull --prefix=release-beacon rb-app main
```

Cette commande accède au réseau, récupère `main` depuis `rb-app` et fusionne
ses changements dans le préfixe `release-beacon/`. Elle peut créer un commit
de fusion dans le parent ; elle ne pousse rien vers GitHub ou GitLab.

Si la fusion réussit, restaurer le travail local uniquement si un stash a
été créé à la première étape :

```bash
git stash apply "$subtree_stash"
git status --short
```

`apply` conserve la sauvegarde dans le stash. Vérifier le contenu restauré
avant toute suppression de cette sauvegarde ; la mise en index antérieure
n'est pas nécessairement rétablie. Si le terminal a été fermé, retrouver
l'entrée `before subtree release-beacon` avec `git stash list` avant de
choisir explicitement la sauvegarde à appliquer.

Si le pull signale des conflits, arrêter la séquence avant la restauration
du stash. Examiner `git status`, résoudre les fichiers signalés, les indexer
explicitement puis terminer la fusion avec `git commit`. Pour abandonner
uniquement une fusion encore en cours, confirmée par `git status` :

```bash
git merge --abort
```

Cette annulation conserve le rattachement `--rejoin` éventuellement créé
avant le pull ainsi que le stash. La restauration du stash peut elle aussi
produire des conflits ; dans ce cas, conserver la sauvegarde pendant leur
résolution.

Les options ont été vérifiées dans l'aide Git installée et un marqueur de
rattachement a été observé dans l'historique local. Aucune opération de stash,
de rattachement, de synchronisation ou d'annulation n'a été exécutée pour
valider cette procédure.

### Relation avec l'historique original

Les commits de `release-beacon-export` sont issus de l'historique de
`alellouc-iot`. Les chemins sont cependant réécrits par le split : le commit
original qui modifiait `release-beacon/app/server/app.py` apparaît dans
l'export comme un commit modifiant `app/server/app.py`.

Pour retrouver le commit parent correspondant à une version exportée :

```bash
git log --follow -- app/server/app.py
git log --all --full-history -- release-beacon/app/server/app.py
```

Le premier parcours s'utilise dans le dépôt exporté. Le second s'utilise dans
le dépôt parent. `git subtree split` ne crée pas une copie indépendante de
l'histoire au sens d'une nouvelle origine : il fabrique une vue filtrée de
l'histoire parent. Les commits restent donc récupérables dans le dépôt parent
tant que celui-ci conserve ses références Git.

## Sortir `release-beacon` du versioning parent

Cette étape est optionnelle. Tant que le dossier reste suivi par
`alellouc-iot`, les modifications peuvent être commités et poussés avec le
dépôt parent, même si une branche subtree est publiée ailleurs.

Après avoir vérifié que le dépôt exporté contient bien l'historique et les
fichiers attendus, retirer le dossier de l'index parent sans supprimer les
fichiers du disque :

```bash
cd /chemin/vers/alellouc-iot
git rm --cached -r release-beacon
printf '\n/release-beacon/\n' >> .gitignore
git add .gitignore
git commit -m "Stop tracking release-beacon in parent repository"
```

`git rm --cached` ne supprime pas le répertoire de travail. Le commit parent
cesse seulement de suivre ces chemins. L'historique antérieur du parent reste
inchangé et les commits précédents restent consultables.

Après cette séparation, le dépôt parent ne peut plus régénérer un subtree à
partir de ce dossier : il ne le suit plus. Les modifications de l'application
doivent être commitée dans le dépôt autonome, puis poussées directement vers
son remote :

```bash
cd /chemin/vers/alellouc-iot/release-beacon
git status

git add .
git commit -m "fix(app): ..."
git push origin main
```

Ce fonctionnement est pratique pour publier une vue filtrée, mais il n'est
pas un remplacement automatique d'un dépôt imbriqué ou d'un submodule. Pour
continuer à utiliser `git subtree split`, il faut conserver le suivi du dossier
dans le parent jusqu'à la fin des exports. Après le retrait du suivi parent, un
clone du dépôt parent ne contient plus automatiquement les fichiers de
`release-beacon`.

## Récupérer et travailler sur Release Beacon depuis le parent

### Parent encore propriétaire du dossier

Si `release-beacon/` est toujours suivi par `alellouc-iot`, un clone normal
du parent suffit :

```bash
git clone git@gitlab.com:AudeizReading/alellouc-iot.git
cd alellouc-iot
```

L'application est alors disponible dans `release-beacon/`. Les modifications
du sous-projet peuvent être vérifiées avec :

```bash
git status --short -- release-beacon
git diff -- release-beacon
```

Le commit est effectué dans le dépôt parent :

```bash
git add release-beacon
git commit -m "fix(project.app): ..."
git push origin HEAD
```

L'export GitHub est ensuite régénéré avec `git subtree split` puis poussé sur
`rb-app`.

### Parent ne suivant plus le dossier

Dans ce mode, le dépôt parent ne peut pas restaurer `release-beacon/` par un
clone ordinaire. Le dépôt autonome doit être cloné à l'emplacement attendu :

```bash
git clone \
  git@github.com:AudeizReading/alellouc-iot-release-beacon.git \
  alellouc-iot/release-beacon
```

Le clone est alors un dépôt Git imbriqué. Les opérations Git de l'application
doivent être lancées depuis `alellouc-iot/release-beacon`, et les opérations
du projet global depuis `alellouc-iot`.

Cette solution évite un submodule, mais elle impose une étape de récupération
manuelle. Elle est compatible avec un environnement où un clone externe ne
doit pas être rapatrié automatiquement par le dépôt principal. Pour la
livraison scolaire, le dépôt parent reste la référence à cloner selon les
règles du projet ; le dépôt autonome est une vue de travail ou de publication
à récupérer séparément lorsque cela est autorisé.

## Versionnement et changements

La version applicative est définie dans
[`app/pyproject.toml`](app/pyproject.toml). Le tag Docker ne modifie pas cette
valeur. Une reconstruction v1 ou v2 doit donc utiliser le contenu Git
correspondant de l'application et la valeur de version attendue avant de
construire l'image.

Avant une construction ou une publication :

```bash
git status --short
git diff -- app/pyproject.toml app/appli app/server
```

Le nom par défaut du fichier de release est construit à partir du contexte,
du nom et du tag :

```text
<contexte>/img/release/digest/<nom>-<tag>.release.yaml
```

Avec la commande P3 ci-dessus, il s'agit donc de
`release-beacon/img/release/digest/release-beacon-v1.release.yaml`. Le fichier
doit contenir le digest réellement produit, et non un tag seul. Une image publiée sur une
registry et un manifeste GitOps doivent être associés au même changement
vérifiable.

## Limites actuelles

- Un workflow indépendant de vérification des PR avec Python et uv est fourni ;
  les contrôles et la protection de branche à activer sont décrits dans
  [le guide CI](.github/CI.md).
- Le workflow GitHub de construction, de signature et de publication du digest
  est fourni ; son exécution sur GitHub reste à vérifier. La configuration et
  la procédure de release sont décrites dans [le guide dédié](.github/RELEASES.md).
- Les constructions locales restent disponibles avec Docker depuis le dépôt
  autonome ou avec le playbook Ansible/Mise depuis `alellouc-iot`.
- `git subtree split` ne sélectionne que le préfixe
  `release-beacon/`. Il ne permet pas d'extraire arbitrairement des fichiers
  situés à côté du préfixe.
- L'export subtree n'est pas récupéré automatiquement par un clone du parent
  après retrait du suivi parent.
