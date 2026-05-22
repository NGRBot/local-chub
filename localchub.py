import os, json, base64, requests, re, random, argparse, time, threading, datetime, struct, zlib, io
from flask import Flask, render_template, request, send_from_directory, jsonify, Response
from PIL import Image, UnidentifiedImageError

app = Flask(__name__)

CARDS_PER_PAGE = 50
CARD_PREVIEW_SIZE = (300, 300)

parser = argparse.ArgumentParser()
parser.add_argument('--autoupdate', type=int, default=None, nargs='?', const=60, help='Auto-update interval in seconds')
parser.add_argument('--synctags', action='store_true', default=False, help='Enable tag synchronization')
parser.add_argument('--backup', action='store_true', default=False, help='Backup old cards to /backup')
args = parser.parse_args()
autoupdInterval = args.autoupdate
autoupdMode = args.autoupdate is not None
synctagsMode = args.synctags
backupMode = args.backup
autoupdThread = None

def autoUpdate():
    while True:
        print(f'[autoupdate/{autoupdInterval}s] Updating cards..')
        try:
            requests.get('http://127.0.0.1:1401/sync')
        except requests.ConnectionError:
            pass
        time.sleep(autoupdInterval)

def deleteCard(cardId):
    for ext in ['png', 'json']:
        os.remove(f'static/{cardId}.{ext}')

def getCardMetadata(cardId):
    with open(f'static/{cardId}.json', 'r', encoding='utf-8') as f:
        metadata = json.load(f)
        return metadata

def getPngInfo(cardId):
    with open(f'static/{cardId}.png', 'rb') as f:
        img = Image.open(f)
        return json.loads(base64.b64decode(img.png.im_info['chara']).decode('utf-8'))

def pngCheck(cardId):
    try:
        Image.open(f'static/{cardId}.png').format == 'PNG'
        return True
    except UnidentifiedImageError:
        return False

def createCardEntry(metadata):
    return {
        'id': metadata['id'],
        'author': metadata['fullPath'].split('/')[0],
        'name': metadata['name'],
        'tagline': metadata['tagline'],
        'description': metadata['description'].replace('Creator\'s notes go here.', '\n'),
        'topics': [topic for topic in metadata['topics'] if topic != 'ROOT'],
        'imagePath': f'static/{metadata["id"]}.png',
        'tokenCount': metadata['nTokens'],
        'lastActivityAt': datetime.datetime.strptime(metadata['lastActivityAt'], "%Y-%m-%dT%H:%M:%SZ").strftime("%B %d, %Y %H:%M")
    }

def getCardList(page, query=None, searchType='basic'):
    cards = []
    all_names = [f.split('.')[0] for f in os.listdir('static') if f.lower().endswith('.png')]

    def card_sort_key(name):
        if name.startswith('IMPORT'):
            try:
                return (1, -int(name[6:]))
            except ValueError:
                return (2, name)
        try:
            return (0, -int(name))
        except ValueError:
            return (2, name)

    cardIds = sorted(all_names, key=card_sort_key)
    count = len(cardIds)
    randomTags = set()

    if query:
        for cardId in cardIds:
            metadata = getCardMetadata(cardId)
            randomTags.update(metadata['topics'])

            if searchType == 'tag' and all(tag.strip() in [tag.lower() for tag in metadata['topics']] for tag in query.lower().split(',')):
                cards.append(createCardEntry(metadata))
            elif searchType == 'author' and query.strip().lower() == metadata['fullPath'].split('/')[0].lower():
                cards.append(createCardEntry(metadata))
            elif searchType == 'title' and query.strip().lower() in metadata['name'].lower():
                cards.append(createCardEntry(metadata))
            elif searchType == 'random':
                cnt = int(re.search(r'\d+', query)[0]) if re.search(r'\d+', query) else 10
                for i in range(cnt):
                    [cards.append(createCardEntry(getCardMetadata(random.choice(cardIds))))]
                break
            elif searchType == 'basic' and all(query.strip().lower() in metadata['name'].lower() or query.strip().lower() in metadata['tagline'].lower() or query.strip().lower() in metadata['description'].lower() or query.strip().lower() in [tag.lower() for tag in metadata['topics']] for query in query.lower().split(',')):
                cards.append(createCardEntry(metadata))

    else:
        startIndex = (page - 1) * CARDS_PER_PAGE
        endIndex = startIndex + CARDS_PER_PAGE
        for cardId in cardIds[startIndex:endIndex]:
            metadata = getCardMetadata(cardId)
            if metadata:
                randomTags.update(metadata['topics'])
                cards.append(createCardEntry(metadata))

    if randomTags:
        randomTags = random.sample(list(randomTags), min(10, len(randomTags)))
    else:
        randomTags = []
    return cards, count, randomTags

def savePngInfo(cardId, card_data):
    encoded = base64.b64encode(json.dumps(card_data).encode('utf-8')).decode('ascii')

    with open(f'static/{cardId}.png', 'rb') as f:
        png_data = f.read()

    signature = png_data[:8]
    chunks_raw = png_data[8:]

    keyword = b'chara'
    separator = b'\x00'
    new_chunk_data_raw = keyword + separator + encoded.encode('latin-1')
    new_chunk_type = b'tEXt'

    crc_data = new_chunk_type + new_chunk_data_raw
    new_crc = struct.pack('>I', zlib.crc32(crc_data) & 0xFFFFFFFF)

    result = bytearray(signature)
    i = 0
    replaced = False
    while i < len(chunks_raw):
        length = struct.unpack('>I', chunks_raw[i:i+4])[0]
        chunk_type = chunks_raw[i+4:i+8]
        chunk_data = chunks_raw[i+8:i+8+length]

        if chunk_type == b'tEXt' and chunk_data.startswith(b'chara\x00'):
            result += struct.pack('>I', len(new_chunk_data_raw))
            result += new_chunk_type
            result += new_chunk_data_raw
            result += new_crc
            replaced = True
        else:
            result += chunks_raw[i:i+12+length]

        i += 12 + length

    if not replaced:
        raise ValueError('No chara chunk found in PNG')

    with open(f'static/{cardId}.png', 'wb') as f:
        f.write(result)

def blacklistAdd(cardId):
    if not os.path.exists('blacklist.txt'):
        with open('blacklist.txt', 'w') as f:
            f.write('')
    with open('blacklist.txt', 'a') as f:
        f.write(f'{cardId}\n')

def blacklistCheck(cardId):
    if os.path.exists('blacklist.txt'):
        with open('blacklist.txt', 'r') as f:
            return cardId in f.read().split('\n')
    return False

def getNextCardId():
    max_num = 0
    for f in os.listdir('static'):
        if not f.lower().endswith('.png'):
            continue
        name = f.split('.')[0]
        if name.startswith('IMPORT'):
            try:
                n = int(name[6:])
                if n > max_num:
                    max_num = n
            except ValueError:
                continue
    return f'IMPORT{max_num + 1}'

def generateGreyPlaceholder(cardId):
    img = Image.new('RGB', CARD_PREVIEW_SIZE, color=(169, 169, 169))
    img.save(f'static/{cardId}.png')

@app.route('/import', methods=['POST'])
def import_cards():
    files = request.files.getlist('files')
    if not files:
        return jsonify({'success': False, 'error': 'No files provided'}), 400

    results = []

    for file in files:
        if file.filename.lower().endswith('.png'):
            temp_data = file.read()

            try:
                img = Image.open(io.BytesIO(temp_data))
                chara_b64 = img.png.im_info['chara']
                chara_data = json.loads(base64.b64decode(chara_b64).decode('utf-8'))
            except (KeyError, Exception):
                results.append({'success': False, 'filename': file.filename, 'error': 'No JSON Data Detected'})
                continue

            card_id = getNextCardId()

            with open(f'static/{card_id}.png', 'wb') as f:
                f.write(temp_data)

            data = chara_data.get('data', {})
            name = data.get('name', os.path.splitext(file.filename)[0])
            description = data.get('description', '')
            tags = data.get('tags', ['IMPORTED'])

            metadata = {
                'id': card_id,
                'name': name,
                'fullPath': f'imported/{name.lower().replace(" ", "-")}',
                'description': description,
                'tagline': description[:100] if description else '',
                'topics': tags,
                'nTokens': 0,
                'lastActivityAt': datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                'imported': True
            }

            with open(f'static/{card_id}.json', 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=4)

            results.append({'success': True, 'filename': file.filename, 'cardId': card_id, 'type': 'png'})

        elif file.filename.lower().endswith('.json'):
            try:
                metadata = json.load(file)
            except Exception:
                results.append({'success': False, 'filename': file.filename, 'error': 'Invalid JSON'})
                continue

            card_id = getNextCardId()
            metadata['id'] = card_id
            metadata['imported'] = True

            name = os.path.splitext(file.filename)[0]
            metadata.setdefault('name', name)
            metadata.setdefault('fullPath', f'imported/{name.lower().replace(" ", "-")}')
            metadata.setdefault('description', '')
            metadata.setdefault('tagline', '')
            metadata.setdefault('topics', ['IMPORTED'])
            metadata.setdefault('nTokens', 0)
            metadata.setdefault('lastActivityAt', datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))

            with open(f'static/{card_id}.json', 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=4)

            generateGreyPlaceholder(card_id)

            results.append({'success': True, 'filename': file.filename, 'cardId': card_id, 'type': 'json'})

    return jsonify({'results': results})

@app.route('/static/<path:filename>', methods=['GET'])
def image(filename):
    return send_from_directory('static', filename)

@app.route('/get_png_info/<cardId>', methods=['GET'])
def get_png_info(cardId):
    png_info = getPngInfo(cardId)
    return jsonify(png_info)

@app.route('/', methods=['GET'])
def index():
    page = int(request.args.get('page', 1))
    query = request.args.get('query')
    searchType = request.args.get('type')
    cards, count, randomTags = getCardList(page, query, searchType)

    search_results = None
    if query:
        search_results = [card for card in cards]

    return render_template('index.html', cards=cards, page=page, card_preview_size=CARD_PREVIEW_SIZE, search_results=search_results, count=count, random_tags=randomTags)

@app.route('/sync', methods=['GET'])
def syncCards():
    author = request.args.get('author', '').strip()
    if not author:
        return Response("data: {\"error\": \"Author name is required\"}\n\n", content_type='text/event-stream')

    totalCards, currCard, newCards = int(request.args.get('c', 500)), 0, 0
    cardIds = sorted([int(file.split('.')[0]) for file in os.listdir('static') if file.lower().endswith('.png') and not file.split('.')[0].startswith('IMPORT')], reverse=True)

    def dlCard(card):
        nonlocal newCards, currCard
        cardId = card['id']
        pTask = 'Downloading'
        if synctagsMode and os.path.exists(f'static/{cardId}.json') and len(card['topics']) > 0:
            if card['topics'] != getCardMetadata(card['id'])['topics']:
                with open(f'static/{cardId}.json', 'w', encoding='utf-8') as f:
                    f.write(json.dumps(card, indent=4))
                    print(f'Updating tags for {card["name"]} ({cardId})..')

        if card['createdAt'] != card['lastActivityAt'] and os.path.exists(f'static/{cardId}.json'):
            if card['lastActivityAt'] != getCardMetadata(card['id'])['lastActivityAt']:
                try:
                    cardIds.remove(cardId)
                    pTask = 'Updating'
                    if backupMode:
                        if not os.path.exists('backup'): os.mkdir('backup')
                        for ext in ['png', 'json']:
                            os.rename(f'static/{cardId}.{ext}', f'backup/{cardId}_{getCardMetadata(card["id"])["lastActivityAt"].split("T")[0]}.{ext}')
                except Exception as e:
                    print(e, cardId)

        if cardId not in cardIds:
            with open(f'static/{cardId}.json', 'w', encoding='utf-8') as f:
                f.write(json.dumps(card, indent=4))
            resp = requests.get(card['max_res_url'])
            if resp.status_code != 200:
                print(f'Failed to download image for {card["name"]} ({cardId}) - HTTP {resp.status_code}')
                os.remove(f'static/{cardId}.json')
                return False
            with open(f'static/{cardId}.png', 'wb') as f:
                f.write(resp.content)
                print(f'{pTask} {card["name"]} ({cardId})..')
            if not pngCheck(cardId):
                deleteCard(cardId)
                print(f'Invalid image for {card["name"]} ({cardId}) - not a valid PNG, skipping')
                return False
            newCards += 1
        currCard += 1
        return True

    def genSyncData():
        nonlocal totalCards
        page = 1
        r = requests.get('https://api.chub.ai/search', params={'first': totalCards, 'page': f'{page}', 'sort': 'last_activity_at', 'venus': 'false', 'asc': 'false', 'nsfw': 'true', 'min_tokens': '50', 'username': author, 'include_forks': 'true'}, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}).json()
        cards = r['data']['nodes']
        for card in cards:
            yield f"data: {json.dumps({'progress': round((currCard / len(cards)) * 100, 2), 'currCard': card['name'], 'newCards': newCards})}\n\n"
            if not blacklistCheck(str(card['id'])):
                if card['id'] == 88:
                    continue
                if not dlCard(card):
                    continue

        yield f"data: {json.dumps({'progress': 100, 'currCard': 'Sync Completed', 'newCards': newCards})}\n\n"

    return Response(genSyncData(), content_type='text/event-stream')

@app.route('/delete_card/<cardId>', methods=['POST', 'DELETE'])
def delete_card(cardId):
    try:
        deleteCard(cardId)
        if cardId.isdigit():
            blacklistAdd(cardId)
        return jsonify({'message': 'Card deleted successfully'}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/edit_tags/<cardId>', methods=['POST'])
def edit_tags(cardId):
    try:
        newTags = request.form.get('tags')
        metadata = getCardMetadata(cardId)
        metadata['topics'] = [tag.strip() for tag in newTags.split(',') if tag != '']
        with open(f'static/{cardId}.json', 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=4)
        return jsonify({'message': 'Tags updated successfully'}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/edit_card/<cardId>', methods=['POST'])
def edit_card(cardId):
    try:
        updates = request.get_json()

        img = Image.open(f'static/{cardId}.png')
        card_data = json.loads(base64.b64decode(img.png.im_info['chara']).decode('utf-8'))

        for key, value in updates.items():
            if key in card_data['data']:
                card_data['data'][key] = value

        savePngInfo(cardId, card_data)

        return jsonify({'message': 'Card updated successfully'}), 200
    except FileNotFoundError:
        return jsonify({'message': 'Card not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 500

if __name__ == '__main__':
    if autoupdMode:
        autoupdThread = threading.Thread(target=autoUpdate)
        autoupdThread.daemon = True
        autoupdThread.start()

    app.run(debug=True, port=1401)