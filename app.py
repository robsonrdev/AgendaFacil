import os
from datetime import datetime, timedelta
# Importações para lidar com arquivos de imagem com segurança
from werkzeug.utils import secure_filename 
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from sqlalchemy import select

basedir = os.path.abspath(os.path.dirname(__file__))

# --- CONFIGURAÇÃO DE UPLOAD DE IMAGENS ---
UPLOAD_FOLDER = os.path.join(basedir, 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chave-secreta-dev'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'saas.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER # Onde salvar as imagens

# Cria a pasta de uploads se ela não existir
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

# Função auxiliar para verificar extensão de arquivo
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- MODELOS (BANCO DE DADOS) ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    senha = db.Column(db.String(100), nullable=False)
    nome = db.Column(db.String(100))
    # Relacionamento genérico com 'Business'
    business = db.relationship('Business', backref='dono', uselist=False, lazy=True)

class Business(db.Model):
    __tablename__ = 'business'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    nome_loja = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    
    # Personalização Visual Avançada
    cor_fundo = db.Column(db.String(7), default='#f4f4f4')
    cor_botao = db.Column(db.String(7), default='#28a745') # Nova cor para botões
    img_fundo = db.Column(db.String(255), nullable=True)   # Caminho da imagem de fundo
    img_logo = db.Column(db.String(255), nullable=True)    # Caminho da logo
    
    # Horários
    abertura = db.Column(db.String(5), default='08:00')
    fechamento = db.Column(db.String(5), default='19:00')
    trabalha_sabado = db.Column(db.Boolean, default=True)
    trabalha_domingo = db.Column(db.Boolean, default=False)
    
    servicos = db.relationship('Servico', backref='business', lazy=True)
    agendamentos = db.relationship('Agendamento', backref='business', lazy=True)

class Servico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    nome = db.Column(db.String(50), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    duracao = db.Column(db.Integer, default=30) 

class Agendamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    cliente_nome = db.Column(db.String(100), nullable=False)
    servico_nome = db.Column(db.String(255), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    data_hora_inicio = db.Column(db.DateTime, nullable=False)
    data_hora_fim = db.Column(db.DateTime, nullable=False)
    observacao = db.Column(db.String(255), nullable=True) # Observação do cliente

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/')
def index():
    if current_user.is_authenticated: return redirect(url_for('verificar_loja'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    user = User.query.filter_by(email=request.form.get('email')).first()
    if user and user.senha == request.form.get('senha'):
        login_user(user)
        return redirect(url_for('verificar_loja'))
    flash('Erro no login')
    return redirect(url_for('index'))

@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if request.method == 'POST':
        novo = User(email=request.form.get('email'), senha=request.form.get('senha'), nome=request.form.get('nome'))
        db.session.add(novo)
        db.session.commit()
        login_user(novo)
        return redirect(url_for('verificar_loja'))
    return render_template('registrar.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# --- ROTAS DE GERENCIAMENTO DA EMPRESA ---

@app.route('/verificar_loja')
@login_required
def verificar_loja():
    if current_user.business: return redirect(url_for('dashboard'))
    return render_template('criar_loja.html')

@app.route('/criar_loja_action', methods=['POST'])
@login_required
def criar_loja_action():
    slug = request.form.get('slug').lower().strip().replace(' ', '-')
    sabado = True if request.form.get('sabado') else False
    domingo = True if request.form.get('domingo') else False

    nova = Business(
        nome_loja=request.form.get('nome'), slug=slug, user_id=current_user.id,
        abertura=request.form.get('abertura'), fechamento=request.form.get('fechamento'),
        trabalha_sabado=sabado, trabalha_domingo=domingo
    )
    db.session.add(nova)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    business = current_user.business
    if not business: return redirect(url_for('verificar_loja'))
    
    agendamentos = Agendamento.query.filter_by(business_id=business.id).order_by(Agendamento.data_hora_inicio).all()
    servicos = Servico.query.filter_by(business_id=business.id).all()
    faturamento = sum(a.valor for a in agendamentos)
    
    # Passamos 'loja' para o template para manter compatibilidade com o HTML existente
    return render_template('dashboard.html', loja=business, agendamentos=agendamentos, servicos=servicos, faturamento=faturamento)

# --- ROTA DE PERSONALIZAÇÃO (CORES + UPLOAD) ---
@app.route('/personalizar', methods=['POST'])
@login_required
def personalizar():
    business = current_user.business
    
    # Atualiza Cores
    business.cor_fundo = request.form.get('cor_fundo')
    business.cor_botao = request.form.get('cor_botao')
    
    # Upload Imagem de Fundo
    if 'img_fundo' in request.files:
        file = request.files['img_fundo']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(f"bg_{business.id}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            business.img_fundo = filename

    # Upload Logo
    if 'img_logo' in request.files:
        file = request.files['img_logo']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(f"logo_{business.id}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            business.img_logo = filename

    db.session.commit()
    return redirect(url_for('dashboard'))

# --- ROTAS DE SERVIÇOS E HORÁRIOS ---

@app.route('/atualizar_horarios', methods=['POST'])
@login_required
def atualizar_horarios():
    business = current_user.business
    business.abertura = request.form.get('abertura')
    business.fechamento = request.form.get('fechamento')
    business.trabalha_sabado = True if request.form.get('sabado') else False
    business.trabalha_domingo = True if request.form.get('domingo') else False
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/adicionar_servico', methods=['POST'])
@login_required
def adicionar_servico():
    business = current_user.business
    nome = request.form.get('nome')
    preco = request.form.get('preco')
    duracao = request.form.get('duracao')
    if nome and preco and duracao:
        novo = Servico(business_id=business.id, nome=nome, preco=float(preco), duracao=int(duracao))
        db.session.add(novo)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/atualizar_preco_servico/<int:servico_id>', methods=['POST'])
@login_required
def atualizar_preco_servico(servico_id):
    servico = db.session.get(Servico, servico_id)
    if servico and servico.business_id == current_user.business.id:
        novo_preco = request.form.get('novo_preco')
        if novo_preco:
            servico.preco = float(novo_preco)
            db.session.commit()
            flash('Preço atualizado!')
    return redirect(url_for('dashboard'))

@app.route('/excluir_servico/<int:servico_id>')
@login_required
def excluir_servico(servico_id):
    servico = db.session.get(Servico, servico_id)
    if servico and servico.business_id == current_user.business.id:
        db.session.delete(servico)
        db.session.commit()
    return redirect(url_for('dashboard'))

# --- ROTA PARA CANCELAR AGENDAMENTO ---
@app.route('/excluir_agendamento/<int:agendamento_id>')
@login_required
def excluir_agendamento(agendamento_id):
    agendamento = db.session.get(Agendamento, agendamento_id)
    if agendamento and agendamento.business_id == current_user.business.id:
        db.session.delete(agendamento)
        db.session.commit()
        flash('Cancelado com sucesso.')
    return redirect(url_for('dashboard'))

# --- ROTA PARA GERAR COMPROVANTE (TICKET) ---
@app.route('/gerar_comprovante/<int:agendamento_id>')
@login_required
def gerar_comprovante(agendamento_id):
    agendamento = db.session.get(Agendamento, agendamento_id)
    if not agendamento or agendamento.business_id != current_user.business.id:
        return "Erro: Agendamento não encontrado ou sem permissão."
    
    business = current_user.business
    
    # Renderiza o template bonito, passando 'modo_visualizacao=True' para esconder botões do cliente
    return render_template('sucesso.html', 
                           loja=business, 
                           agendamento=agendamento,
                           data_formatada=agendamento.data_hora_inicio.strftime('%d/%m/%Y às %H:%M'),
                           modo_visualizacao=True)

# --- VISÃO DO CLIENTE (PÚBLICA) ---

@app.route('/<slug>')
def visao_cliente(slug):
    business = Business.query.filter_by(slug=slug).first_or_404()
    servicos = Servico.query.filter_by(business_id=business.id).all()
    # Passa 'loja' para o template para manter compatibilidade
    return render_template('agendar.html', loja=business, servicos=servicos)

@app.route('/api/horarios_disponiveis/<int:business_id>')
def get_horarios(business_id):
    data_str = request.args.get('data')
    servico_ids_str = request.args.get('servico_ids')
    if not servico_ids_str or not data_str: return jsonify([])

    business = db.session.get(Business, business_id)
    try:
        servico_ids = [int(id) for id in servico_ids_str.split(',')]
        data_escolhida = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError: return jsonify([])
    
    # 1. Calcula duração total dos serviços selecionados
    servicos_selecionados = db.session.execute(select(Servico).where(Servico.id.in_(servico_ids))).scalars().all()
    total_duration = sum(s.duracao for s in servicos_selecionados)
    if total_duration == 0: return jsonify([])

    # 2. Define limites do dia
    hora_abertura = datetime.strptime(business.abertura, '%H:%M').time()
    hora_fechamento = datetime.strptime(business.fechamento, '%H:%M').time()
    
    dia_semana = data_escolhida.weekday()
    if dia_semana == 5 and not business.trabalha_sabado: return jsonify([])
    if dia_semana == 6 and not business.trabalha_domingo: return jsonify([])

    inicio_dia = datetime.combine(data_escolhida, hora_abertura)
    fim_dia = datetime.combine(data_escolhida, hora_fechamento)
    
    # 3. Busca agendamentos existentes
    agendamentos = db.session.execute(select(Agendamento).where(
        Agendamento.business_id == business_id,
        Agendamento.data_hora_inicio >= inicio_dia,
        Agendamento.data_hora_inicio <= fim_dia
    )).scalars().all()

    # 4. Gera slots livres
    slots_disponiveis = []
    atual = inicio_dia
    duracao_servico = timedelta(minutes=total_duration)
    
    while atual + duracao_servico <= fim_dia:
        horario_livre = True
        fim_do_servico = atual + duracao_servico
        for agendamento in agendamentos:
            if atual < agendamento.data_hora_fim and fim_do_servico > agendamento.data_hora_inicio:
                horario_livre = False
                break
        if horario_livre: slots_disponiveis.append(atual.strftime('%H:%M'))
        atual += timedelta(minutes=30) 
    return jsonify(slots_disponiveis)

@app.route('/confirmar_agendamento/<int:business_id>', methods=['POST'])
def confirmar_agendamento(business_id):
    cliente = request.form.get('cliente')
    data_str = request.form.get('data')
    hora_str = request.form.get('hora')
    servico_ids_str = request.form.getlist('servico_ids')
    observacao = request.form.get('observacao')
    
    if not servico_ids_str or not hora_str: return "Erro: Selecione serviço(s) e horário."

    servico_ids = [int(id) for id in servico_ids_str]
    servicos_selecionados = db.session.execute(select(Servico).where(Servico.id.in_(servico_ids))).scalars().all()
    
    total_duration = sum(s.duracao for s in servicos_selecionados)
    total_price = sum(s.preco for s in servicos_selecionados)
    service_names = " + ".join(s.nome for s in servicos_selecionados)
    
    inicio = datetime.strptime(f"{data_str} {hora_str}", '%Y-%m-%d %H:%M')
    fim = inicio + timedelta(minutes=total_duration)
    
    novo = Agendamento(
        business_id=business_id,
        cliente_nome=cliente,
        servico_nome=service_names,
        valor=total_price,
        data_hora_inicio=inicio,
        data_hora_fim=fim,
        observacao=observacao
    )
    db.session.add(novo)
    db.session.commit()
    
    # Busca a loja para pegar as cores/logo
    business = db.session.get(Business, business_id)
    
    # Retorna o template bonito
    return render_template('sucesso.html', 
                           loja=business, 
                           agendamento=novo,
                           data_formatada=inicio.strftime('%d/%m/%Y às %H:%M'))

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True)