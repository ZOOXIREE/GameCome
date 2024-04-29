from flask_login import login_user, logout_user, login_required, current_user, LoginManager, UserMixin
from flask import Flask
from flask import redirect, request, render_template, session, jsonify
from pathlib import Path
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import subqueryload

# создаем объект класса Flask
BASE_DIR = Path(__file__).resolve(strict=True).parent
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + str(BASE_DIR / 'instance/biography.db')
app.secret_key = "dsfknkdsnauolfgsdbolfdsj"
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# создаём модель таблицы БД
class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    comments = db.relationship('GameComment', backref='game', lazy=True)
    images = db.relationship('GameImage', backref='game', lazy=True)  # Новая связь для изображений


# Определите модель GameImage
class GameImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    image_url = db.Column(db.String, nullable=False)  # храним URL изображения


class GameComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)  # Имя пользователя, оставившего комментарий
    text = db.Column(db.Text, nullable=False)  # Текст комментария
    date = db.Column(db.DateTime, default=datetime.utcnow)  # Дата и время комментария
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    recommendation = db.Column(db.String(20), nullable=False)

    def __repr__(self):
        return f'<GameComment {self.id}>'


# создаём модель таблицы БД
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(50), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    is_active = db.Column(db.Boolean, default=True)


# Регистрация пользователя
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        fullname = request.form['fullname']

        # Проверяем, существует ли уже пользователь с таким именем или полным именем
        existing_username = User.query.filter_by(username=username).first()
        existing_fullname = User.query.filter_by(fullname=fullname).first()

        if existing_username:
            error = "Пользователь с таким именем уже существует. Пожалуйста, выберите другое имя пользователя."
            return render_template('register.html', error=error)
        elif existing_fullname:
            error = "Пользователь с таким полным именем уже существует. Пожалуйста, выберите другое полное имя."
            return render_template('register.html', error=error)

        # Если пользователей с таким именем или полным именем нет, продолжаем регистрацию
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password, fullname=fullname)

        try:
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)  # Автоматическая авторизация нового пользователя
            session['username'] = username
            return redirect('/')
        except IntegrityError:
            db.session.rollback()
            error = "Ошибка при регистрации. Пожалуйста, попробуйте снова."
            return render_template('register.html', error=error)

    return render_template('register.html')


# Вход пользователя
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = False  # Переменная для отслеживания ошибки
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)  # Устанавливаем пользователя в сессию
            session['username'] = username
            return redirect('/')
        else:
            error = True
    return render_template('login.html', error=error)


# Выход пользователя
@app.route('/logout')
def logout():
    if current_user.is_authenticated:
        logout_user()
    session.pop('username', None)
    return redirect('/')


message_admin: list[tuple] = list()


# отслеживание URL вкладки
@app.route("/")
@app.route("/home")
def home():
    return render_template('home.html')


# отслеживание URL вкладки О сайте
@app.route("/about")
def about():
    return render_template('about.html')


# отслеживание URL вкладки Главная
@app.route('/posts')
def comments():
    games_data = []
    games = Game.query.options(subqueryload(Game.images)).all()

    for game in games:
        if game.images:
            image_url = game.images[0].image_url
        else:
            image_url = None  # Или задать URL изображения по умолчанию

        games_data.append({
            'game_id': game.id,
            'game_name': game.name,
            'image_url': image_url,
            'comment_count': len(game.comments),
        })

    return render_template('posts.html', games_data=games_data)


# комментарий к игре
@app.route('/game/<int:game_id>/comments')
def game_comments(game_id):
    game = Game.query.get_or_404(game_id)
    comments = GameComment.query.filter_by(game_id=game_id).all()
    return render_template('game_comments.html', game=game, comments=comments)


# Добавление комментария
@app.route('/add-comment', methods=['GET', 'POST'])
@login_required
def add_comment():
    if request.method == 'POST':
        text = request.form.get('text')
        game_id = request.form.get('game')
        username = current_user.fullname if current_user.is_authenticated else None
        recommendation = request.form.get('recommendation')  # Используйте метод get для безопасного извлечения значения

        if not text or not game_id or not recommendation:
            return jsonify(
                {'success': False, 'error': 'Отсутствует информация о игре, тексте комментария или рекомендации.'})

        game = Game.query.get(game_id)
        if not game:
            return jsonify({'success': False, 'error': 'Игра не найдена.'})

        existing_comment = GameComment.query.filter_by(username=username, game_id=game.id).first()
        if existing_comment:
            return jsonify({'success': False, 'error': 'Вы уже оставляли комментарий к этой игре.'})

        try:
            new_comment = GameComment(username=username, text=text, game_id=game.id, recommendation=recommendation)
            db.session.add(new_comment)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Комментарий успешно добавлен.'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': f'Ошибка при добавлении комментария: {str(e)}'})
    else:
        # Этот блок кода обрабатывает GET запрос
        games = Game.query.order_by(Game.name).all()  # Получение списка всех игр
        return render_template('add_comment.html', games=games)


@app.route('/api_search_games')
def api_search_games():
    game_name = request.args.get('game_name', '').strip().lower()
    games = Game.query.filter(Game.name.ilike(f"%{game_name}%")).all()
    return jsonify([{'id': game.id, 'name': game.name} for game in games])


@app.route('/search', methods=['GET'])
def search():
    search_query = request.args.get('query', '').strip().lower()
    games = Game.query.filter(Game.name.ilike(f"%{search_query}%")).all()
    games_data = []

    for game in games:
        if game.images:
            image_url = game.images[0].image_url
        else:
            image_url = None  # или установите URL изображения по умолчанию

        games_data.append({
            'game_id': game.id,
            'game_name': game.name,
            'image_url': image_url,
        })

    print(games_data)  # Проверяем данные перед отправкой в шаблон
    print(search_query)  # Проверяем запрос перед отправкой в шаблон

    return render_template('search_results.html', games_data=games_data, query=search_query)



# обработчик URL для изменения комментария
@app.route('/comments/<int:id>/update', methods=['POST', 'GET'])
def update_comment(id):
    comment = GameComment.query.get_or_404(id)

    if request.method == 'POST':
        comment.text = request.form['text']

        try:
            db.session.commit()
            return redirect('/posts')
        except:
            return "При изменении произошла ошибка"

    return render_template('comment_update.html', comment=comment)


# отслеживание URL вкладки, отправляющей жалобы
@app.route('/message', methods=["POST", "GET"])
def message():
    global message_admin
    if request.method == "POST":
        url = request.form['url']
        problem = request.form['problem']
        message_admin.append((datetime.now(), url, problem))
    return render_template('message.html')


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

# пояснение к файлам
"""
    home.html - вкладка "Биографи";
    about.html - вкладка "О нас";
    add_biography.html - вкладка для Добавления;
    login.html - вкладка для Входа в Админ аккаунт;
    post_update.html - вкладка Обновления Поста;
    posts.html - вкладка всех Статей;
    main.css - все css стили
    biography.db - БД со всеми статьями
    admin.py - код с Логином и Паролем Админа
    app.py - код Приложения
    db.py - скрипт для создания БД
"""
