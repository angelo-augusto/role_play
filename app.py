# app.py

import random, math
from flask import Flask, render_template, request
import threading, time
from flask_socketio import SocketIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cle_secrete' 
socketio = SocketIO(app)

DIRECTIONS = ['up', 'right', 'down', 'left']

def generate_random_color():
    """Génère une couleur aléatoire en format hexadécimal."""
    return f"#{random.randint(0, 0xFFFFFF):06x}"

def get_player(sid):
    """Fonction utilitaire pour trouver un joueur par son sid."""
    return next((char for char in game_state['characters'] if char.get('id') == sid), None)


# --- L'IA de génération de carte en Python ---
def generate_drunken_map(width, height, steps):
    # 1. Créer une carte pleine de murs (1)
    # C'est l'équivalent du tableau de tableaux en JS
    game_map = [[1 for _ in range(width)] for _ in range(height)]

    # 2. Choisir un point de départ
    current_x = width // 2
    current_y = height // 2
    game_map[current_y][current_x] = 0  # Creuser le sol

    # 3. Marcher aléatoirement
    directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]  # Haut, Bas, Gauche, Droite

    for _ in range(steps):
        dx, dy = random.choice(directions)
        
        # Bouger le marcheur, en s'assurant de rester dans les limites
        current_x = max(1, min(width - 2, current_x + dx))
        current_y = max(1, min(height - 2, current_y + dy))

        game_map[current_y][current_x] = 0
    
    return game_map

def find_place(map):
    map_width= len(map[0])
    map_height= len(map)
    
    x,y = random.randint(0,map_width-1),random.randint(0,map_height-1)
    while map[y][x]==1:
        x,y = random.randint(0,map_width-1),random.randint(0,map_height-1)
    return x,y    
    
def generate_initial_state():
    map = generate_drunken_map(20, 15, 200)
    characters=[]
    x,y = find_place(map)
    characters.append({
        "id":"npc_gobelin",
        "type":"npc",
        "x":x ,
        "y" : y,
        "color": "#3a9d23",
        "direction": random.choice(DIRECTIONS)})
    x,y = find_place(map)
    characters.append({
        "id":"npc_slime",
        "type":"npc",
        "x":x , "y" : y,
        "color": "#4e91a3",
        "direction": random.choice(DIRECTIONS)})
    return {"map":map, "characters":characters}

game_state = generate_initial_state()


def count_players(characters):
    count =0
    for c in characters:
        if c["type"]=="player" :
            count+=1
    return count    

@app.route("/")
def game():
    # La fonction sert juste le template. Les données seront envoyées via WebSocket.
    return render_template("game.html")


@socketio.on('connect')
def handle_connect():
    """Crée un personnage pour le nouveau joueur avec son ID de session."""
    sid = request.sid  # On récupère l'ID de session unique du joueur
    print(f"Un joueur s'est connecté : {sid}")
    
    x, y = find_place(game_state["map"])
    
    # On crée le personnage en utilisant le sid comme identifiant
    new_player = {
        "id": sid,
        "type": "player",
        "x": x,
        "y": y,
        "direction": random.choice(DIRECTIONS),
        "color": generate_random_color()  # Fonction pour générer une couleur aléatoire
        }
    game_state["characters"].append(new_player)

    # On diffuse à tout le monde qu'un nouveau joueur est là
    socketio.emit('update_state', game_state)

@socketio.on('action')
def handle_action(data):
    """Gestionnaire central pour toutes les actions du joueur."""
    player = get_player(request.sid)
    if not player:
        return

    action_type = data.get('type')
    
    # --- PIVOTER ---
    if action_type == 'pivot':
        current_index = DIRECTIONS.index(player['direction'])
        if data['turn'] == 'left':
            new_index = (current_index - 1 + 4) % 4
        else: # 'right'
            new_index = (current_index + 1) % 4
        player['direction'] = DIRECTIONS[new_index]
        # socketio.emit('log_message', {'text': f"{player['id'][:5]}... se tourne."})

    # --- AVANCER ---
    elif action_type == 'advance':
        direction_vectors = {'up': (0, -1), 'right': (1, 0), 'down': (0, 1), 'left': (-1, 0)}
        dx, dy = direction_vectors[player['direction']]
        new_x, new_y = player['x'] + dx, player['y'] + dy

        if game_state["map"][new_y][new_x] == 1:return
        # Vérifier les collisions avec les autres personnages
        if any(c["x"] == new_x and c["y"] == new_y 
               for c in game_state["characters"] if c["id"] != player["id"]):return
        player['x'], player['y'] = new_x, new_y
        # socketio.emit('log_message', {'text': f"{player['id'][:5]}... avance."})

    # --- CRIER ---
    elif action_type == 'shout':
        message = data.get('message', 'AAAAAH!')
        message = 'AAAAAAH!' if message=="" else message
        socketio.emit('log_message', {'text': f"Vous avez crié:{message}"}, to= player['id'])
        # Notifier les joueurs à proximité
        for target in game_state['characters']:
            if target['id'] != player['id']:
                distance = math.hypot(player['x'] - target['x'], player['y'] - target['y'])
                if distance <= 5:
                    socketio.emit('sound_heard', { 'from_id': player['id'], 'message': message} ,to=target['id'])

    # ... D'autres actions (discuter, regarder, attaquer) peuvent être ajoutées ici ...
    
    # Après chaque action, on diffuse le nouvel état à tout le monde
    socketio.emit('update_state', game_state)
 
@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f"Un joueur s'est déconnecté : {sid}")

    # On retire le personnage du joueur de la liste
    initial_len = len(game_state['characters'])
    game_state['characters'] = [char for char in game_state['characters'] if char.get('id') != sid]
    
    # Si un personnage a bien été retiré, on notifie les autres joueurs
    if len(game_state['characters']) < initial_len:
        socketio.emit('update_state', game_state)

def game_loop():
    """Cette fonction tourne en permanence en arrière-plan."""
    while True:
        # On met une pause au début pour que l'émission ne soit pas trop agressive
        time.sleep(1)
        chars = game_state["characters"]
        # Pour chaque personnage dans notre état de jeu
        for char in game_state["characters"]:
            if char["type"] == "npc":
                # ... (votre logique de déplacement reste identique) ...
                choix = random.choice(["left","right","avance"])
                if choix == "left":
                    current_index = DIRECTIONS.index(char['direction'])
                    new_index = (current_index - 1 + 4) % 4
                    char['direction'] = DIRECTIONS[new_index]
                elif choix == "right":
                    current_index = DIRECTIONS.index(char['direction'])
                    new_index = (current_index + 1) % 4
                    char['direction'] = DIRECTIONS[new_index]
                elif choix == "avance":
                    # Avancer dans la direction actuelle
                    direction_vectors = {'up': (0, -1), 'right': (1, 0), 'down': (0, 1), 'left': (-1, 0)}
                    direction= char['direction']
                    dx, dy = direction_vectors[direction]
                    new_x = char['x'] + dx
                    new_y = char['y'] + dy
                    # Vérifier si le mouvement est valide
                    if game_state["map"][new_y][new_x] == 1: continue
                    if any(c["x"] == new_x and c["y"] == new_y for c in chars if c["id"] != char["id"]):
                        continue
                    char['x'] = new_x
                    char['y'] = new_y
        
        # On diffuse le nouvel état à tous les clients connectés.
        socketio.emit('update_state', game_state)
    
        
# On lance la boucle de jeu dans un thread séparé pour ne pas bloquer le serveur
game_thread = threading.Thread(target=game_loop, daemon=True)
game_thread.start()

if __name__ == "__main__":
    # On lance le serveur via socketio
    socketio.run(app, debug=True, port=8000)
    
    
    
#pour la suite 
#gerer les ollisions entre les personnages //OK
#creer un evenement au contact d'un autre perso
