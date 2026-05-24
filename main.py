import discord
from discord.ext import commands
from discord import Embed, Color
import aiohttp
import json
import sqlite3
import asyncio
from datetime import datetime, timedelta
import random
import re
from PIL import Image, ImageDraw, ImageFont
import io

# CONFIGURAÇÕES
TOKEN = 'SEU_TOKEN_AQUI'  # Coloque o token do seu bot aqui
PREFIXO = '.'

# IDs dos donos
DONOS_IDS = [1454636571352498196, 1396816042248114221]

# Configurar intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# Criar bot
bot = commands.Bot(command_prefix=PREFIXO, intents=intents)

# Banco de dados
conn = sqlite3.connect('bot_database.db')
cursor = conn.cursor()

# Criar todas as tabelas existentes...
cursor.execute('''
CREATE TABLE IF NOT EXISTS saldos (
    user_id TEXT PRIMARY KEY,
    saldo REAL DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS verificacoes (
    discord_id TEXT PRIMARY KEY,
    roblox_username TEXT,
    plano TEXT,
    validade TEXT,
    data_verificacao TEXT,
    data_expiracao TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS muted_users (
    user_id TEXT,
    guild_id TEXT,
    end_time TEXT,
    PRIMARY KEY (user_id, guild_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS parcerias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    servidor_id TEXT,
    servidor_nome TEXT,
    servidor_convite TEXT,
    parceiro_id TEXT,
    parceiro_nome TEXT,
    data_parceria TEXT,
    status TEXT DEFAULT 'pendente',
    canal_id TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS parcerias_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    servidor_id TEXT,
    acao TEXT,
    data TEXT
)
''')

# Tabela para galos dos jogadores
cursor.execute('''
CREATE TABLE IF NOT EXISTS galos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    nome_galo TEXT,
    nivel INTEGER DEFAULT 1,
    ataque INTEGER DEFAULT 10,
    defesa INTEGER DEFAULT 10,
    velocidade INTEGER DEFAULT 10,
    hp INTEGER DEFAULT 100,
    hp_atual INTEGER DEFAULT 100,
    experiencia INTEGER DEFAULT 0,
    vitorias INTEGER DEFAULT 0,
    derrotas INTEGER DEFAULT 0,
    imagem_url TEXT,
    is_principal BOOLEAN DEFAULT 0,
    data_criacao TEXT
)
''')

# Tabela para itens da loja
cursor.execute('''
CREATE TABLE IF NOT EXISTS loja_galo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_item TEXT,
    tipo TEXT,
    valor INTEGER,
    bonus_ataque INTEGER DEFAULT 0,
    bonus_defesa INTEGER DEFAULT 0,
    bonus_velocidade INTEGER DEFAULT 0,
    bonus_hp INTEGER DEFAULT 0,
    descricao TEXT
)
''')

# Tabela para inventário dos jogadores
cursor.execute('''
CREATE TABLE IF NOT EXISTS inventario_galo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    item_id INTEGER,
    quantidade INTEGER DEFAULT 1,
    FOREIGN KEY (item_id) REFERENCES loja_galo(id)
)
''')

# Tabela para batalhas ativas
cursor.execute('''
CREATE TABLE IF NOT EXISTS batalhas_galo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canal_id TEXT,
    desafiante_id TEXT,
    desafiado_id TEXT,
    galo_desafiante_id INTEGER,
    galo_desafiado_id INTEGER,
    turno TEXT,
    status TEXT,
    data_inicio TEXT
)
''')

# Adicionar colunas se não existirem
try:
    cursor.execute('ALTER TABLE verificacoes ADD COLUMN data_expiracao TEXT')
except:
    pass

try:
    cursor.execute('ALTER TABLE parcerias ADD COLUMN canal_id TEXT')
except:
    pass

# Inserir itens na loja se não existirem
cursor.execute('SELECT COUNT(*) FROM loja_galo')
if cursor.fetchone()[0] == 0:
    itens_loja = [
        ('Feno Especial', 'alimento', 50, 0, 0, 1, 0, 'Aumenta a velocidade do galo em 1'),
        ('Milho Forte', 'alimento', 100, 1, 0, 0, 0, 'Aumenta o ataque do galo em 1'),
        ('Gergelim Mágico', 'alimento', 150, 0, 1, 0, 0, 'Aumenta a defesa do galo em 1'),
        ('Poção de Vida', 'pocao', 200, 0, 0, 0, 20, 'Aumenta o HP máximo do galo em 20'),
        ('Esporas de Aço', 'equipamento', 300, 3, 0, 0, 0, 'Aumenta o ataque em 3'),
        ('Peitoral Reforçado', 'equipamento', 350, 0, 3, 0, 0, 'Aumenta a defesa em 3'),
        ('Plumas da Velocidade', 'equipamento', 250, 0, 0, 3, 0, 'Aumenta a velocidade em 3'),
        ('Elixir do Guerreiro', 'pocao', 500, 5, 5, 5, 50, 'Aumenta todos os atributos significativamente'),
        ('Cristal de XP', 'especial', 1000, 0, 0, 0, 0, 'Dá 100 de experiência para o galo'),
        ('Galo Lendário', 'skin', 5000, 10, 10, 10, 100, 'Transforma seu galo em uma lenda!'),
    ]
    
    for item in itens_loja:
        cursor.execute('''
        INSERT INTO loja_galo (nome_item, tipo, valor, bonus_ataque, bonus_defesa, bonus_velocidade, bonus_hp, descricao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', item)

conn.commit()

# Variáveis para jogos ativos
jogos_ativos = {}
fake_mutes = {}
batalhas_galo = {}

# ========== FUNÇÕES DOS GALOS ==========

def calcular_poder_galo(nivel, ataque, defesa, velocidade, hp):
    """Calcula o poder total do galo baseado nos atributos"""
    return (nivel * 10) + ataque + defesa + velocidade + (hp // 10)

def calcular_nivel_por_xp(xp):
    """Calcula o nível baseado na experiência"""
    return 1 + (xp // 100)

def calcular_xp_para_proximo_nivel(nivel_atual):
    """Calcula XP necessário para o próximo nível"""
    return nivel_atual * 100

def criar_galo_padrao(nome):
    """Cria um galo padrão para novos jogadores"""
    return {
        'nome': nome,
        'nivel': 1,
        'ataque': 10,
        'defesa': 10,
        'velocidade': 10,
        'hp': 100,
        'hp_atual': 100,
        'xp': 0,
        'vitorias': 0,
        'derrotas': 0
    }

def calcular_dano(atacante, defensor):
    """Calcula dano baseado em fórmula com sorte"""
    base_dano = (atacante['ataque'] - defensor['defesa'] // 2) + random.randint(1, 20)
    return max(5, base_dano)  # Dano mínimo de 5

def ganhar_experiencia(galo_id, xp_ganho):
    """Adiciona experiência ao galo e verifica se subiu de nível"""
    cursor.execute('SELECT nivel, experiencia FROM galos WHERE id = ?', (galo_id,))
    galo = cursor.fetchone()
    
    if galo:
        novo_xp = galo[1] + xp_ganho
        novo_nivel = calcular_nivel_por_xp(novo_xp)
        
        # Aumentar atributos ao subir de nível
        if novo_nivel > galo[0]:
            aumento = novo_nivel - galo[0]
            cursor.execute('''
            UPDATE galos 
            SET experiencia = ?, nivel = ?,
                ataque = ataque + ?,
                defesa = defesa + ?,
                velocidade = velocidade + ?,
                hp = hp + ?,
                hp_atual = hp_atual + ?
            WHERE id = ?
            ''', (novo_xp, novo_nivel, aumento, aumento, aumento, aumento * 10, aumento * 10, galo_id))
        else:
            cursor.execute('UPDATE galos SET experiencia = ? WHERE id = ?', (novo_xp, galo_id))
        
        conn.commit()
        return novo_nivel > galo[0]

# ========== COMANDOS DOS GALOS ==========

@bot.command(name='galo')
async def criar_galo(ctx, nome: str = None):
    """Cria um novo galo para você"""
    if nome is None:
        embed = Embed(
            title='🐔 Criar Galo',
            description=f'Use `{PREFIXO}galo NOME_DO_GALO` para criar seu primeiro galo!',
            color=Color.blue()
        )
        embed.add_field(name='💡 Dica', value='Escolha um nome legal para seu galo guerreiro!')
        await ctx.send(embed=embed)
        return
    
    # Verificar se já tem galo
    cursor.execute('SELECT COUNT(*) FROM galos WHERE user_id = ?', (str(ctx.author.id),))
    count = cursor.fetchone()[0]
    
    if count >= 5:
        await ctx.send('❌ Você já tem 5 galos! Use `.removergalo` para liberar espaço.')
        return
    
    # Criar galo
    cursor.execute('''
    INSERT INTO galos (user_id, nome_galo, nivel, ataque, defesa, velocidade, hp, hp_atual, data_criacao, is_principal)
    VALUES (?, ?, 1, 10, 10, 10, 100, 100, ?, ?)
    ''', (str(ctx.author.id), nome, datetime.now().isoformat(), 1 if count == 0 else 0))
    conn.commit()
    
    galo_id = cursor.lastrowid
    
    # Buscar URL de imagem (gerar imagem de galo nível 1)
    imagem_url = await gerar_imagem_galo(galo_id, nome, 1)
    
    embed = Embed(
        title='🐔 Galo Criado com Sucesso!',
        description=f'Seu galo **{nome}** foi criado!',
        color=Color.green()
    )
    embed.set_thumbnail(url=imagem_url)
    embed.add_field(name='📊 Atributos Iniciais', value=f'⚔️ Ataque: 10\n🛡️ Defesa: 10\n⚡ Velocidade: 10\n❤️ HP: 100', inline=True)
    embed.add_field(name='🎯 Nível', value='1', inline=True)
    embed.add_field(name='💪 Poder', value=calcular_poder_galo(1, 10, 10, 10, 100), inline=True)
    embed.set_footer(text=f'Use .vergalo {nome} para ver detalhes!')
    await ctx.send(embed=embed)

@bot.command(name='vergalo')
async def ver_galo(ctx, nome_galo: str = None):
    """Mostra informações detalhadas do seu galo"""
    if nome_galo is None:
        # Mostrar lista de galos
        cursor.execute('SELECT id, nome_galo, nivel, is_principal FROM galos WHERE user_id = ?', (str(ctx.author.id),))
        galos = cursor.fetchall()
        
        if not galos:
            await ctx.send('❌ Você não tem galos! Use `.galo NOME` para criar um.')
            return
        
        embed = Embed(title='🐔 Seus Galos', description=f'{ctx.author.mention}, aqui estão seus guerreiros:', color=Color.blue())
        
        for g in galos:
            principal = "⭐" if g[3] else ""
            embed.add_field(name=f'{principal} {g[1]}', value=f'Nível: {g[2]}\nID: `{g[0]}`', inline=True)
        
        embed.set_footer(text='Use .vergalo ID ou .vergalo NOME para ver detalhes')
        await ctx.send(embed=embed)
        return
    
    # Buscar galo por nome ou ID
    try:
        galo_id = int(nome_galo)
        cursor.execute('SELECT * FROM galos WHERE id = ? AND user_id = ?', (galo_id, str(ctx.author.id)))
    except:
        cursor.execute('SELECT * FROM galos WHERE nome_galo = ? AND user_id = ?', (nome_galo, str(ctx.author.id)))
    
    galo = cursor.fetchone()
    
    if not galo:
        await ctx.send(f'❌ Galo `{nome_galo}` não encontrado!')
        return
    
    poder = calcular_poder_galo(galo[3], galo[4], galo[5], galo[6], galo[7])
    xp_proximo = calcular_xp_para_proximo_nivel(galo[3])
    
    # Calcular progresso de XP
    progresso = int((galo[9] / xp_proximo) * 20)
    barra = "█" * progresso + "░" * (20 - progresso)
    
    imagem_url = await gerar_imagem_galo(galo[0], galo[2], galo[3])
    
    embed = Embed(
        title=f'🐔 {galo[2]} - Guerreiro Épico',
        description=f'⭐ **Principal**' if galo[13] else '',
        color=Color.gold()
    )
    embed.set_thumbnail(url=imagem_url)
    embed.set_image(url=imagem_url)
    
    embed.add_field(name='📊 Atributos', value=f'''
    ⚔️ **Ataque:** {galo[4]}
    🛡️ **Defesa:** {galo[5]}
    ⚡ **Velocidade:** {galo[6]}
    ❤️ **HP:** {galo[7]}/{galo[8]}
    ''', inline=False)
    
    embed.add_field(name='📈 Progresso', value=f'''
    🎯 **Nível:** {galo[3]}
    📊 **XP:** {galo[9]}/{xp_proximo}
    `{barra}`
    ''', inline=False)
    
    embed.add_field(name='🏆 Estatísticas', value=f'''
    🎮 **Vitórias:** {galo[10]}
    💀 **Derrotas:** {galo[11]}
    💪 **Poder Total:** {poder}
    ''', inline=False)
    
    embed.set_footer(text=f'ID: {galo[0]} | Use .treinargalo para evoluir!')
    await ctx.send(embed=embed)

@bot.command(name='treinargalo')
async def treinar_galo(ctx, galo_id: int = None, tipo: str = 'ataque'):
    """Treina seu galo (gasta saldo para aumentar atributos)"""
    if galo_id is None:
        await ctx.send(f'❌ Use: `{PREFIXO}treinargalo ID_do_galo [ataque/defesa/velocidade/hp]`\nUse `.vergalo` para ver os IDs')
        return
    
    cursor.execute('SELECT * FROM galos WHERE id = ? AND user_id = ?', (galo_id, str(ctx.author.id)))
    galo = cursor.fetchone()
    
    if not galo:
        await ctx.send('❌ Galo não encontrado!')
        return
    
    precos = {
        'ataque': 100,
        'defesa': 100,
        'velocidade': 100,
        'hp': 150
    }
    
    if tipo not in precos:
        await ctx.send('❌ Tipo inválido! Use: ataque, defesa, velocidade, ou hp')
        return
    
    saldo_atual = get_saldo(str(ctx.author.id))
    custo = precos[tipo]
    
    if saldo_atual < custo:
        await ctx.send(f'❌ Saldo insuficiente! Você precisa de R$ {custo:.2f}')
        return
    
    # Aplicar treino
    if tipo == 'ataque':
        novo_valor = galo[4] + 1
        cursor.execute('UPDATE galos SET ataque = ? WHERE id = ?', (novo_valor, galo_id))
        mensagem = f'⚔️ Ataque aumentou de {galo[4]} para {novo_valor}!'
    elif tipo == 'defesa':
        novo_valor = galo[5] + 1
        cursor.execute('UPDATE galos SET defesa = ? WHERE id = ?', (novo_valor, galo_id))
        mensagem = f'🛡️ Defesa aumentou de {galo[5]} para {novo_valor}!'
    elif tipo == 'velocidade':
        novo_valor = galo[6] + 1
        cursor.execute('UPDATE galos SET velocidade = ? WHERE id = ?', (novo_valor, galo_id))
        mensagem = f'⚡ Velocidade aumentou de {galo[6]} para {novo_valor}!'
    elif tipo == 'hp':
        novo_valor = galo[7] + 10
        cursor.execute('UPDATE galos SET hp = ?, hp_atual = hp_atual + 10 WHERE id = ?', (novo_valor, galo_id))
        mensagem = f'❤️ HP máximo aumentou de {galo[7]} para {novo_valor}!'
    
    # Descontar saldo
    add_saldo(str(ctx.author.id), -custo)
    conn.commit()
    
    embed = Embed(
        title='🐔 Treino Concluído!',
        description=mensagem,
        color=Color.green()
    )
    embed.add_field(name='💰 Saldo gasto', value=f'R$ {custo:.2f}', inline=True)
    embed.add_field(name='📊 Saldo restante', value=f'R$ {get_saldo(str(ctx.author.id)):.2f}', inline=True)
    await ctx.send(embed=embed)

@bot.command(name='batalhargalo')
async def batalhar_galo(ctx, oponente: discord.Member, galo_id: int = None):
    """Desafia outro jogador para uma batalha de galos"""
    if oponente is None or oponente == ctx.author:
        await ctx.send(f'❌ Use: `{PREFIXO}batalhargalo @usuario ID_do_seu_galo`')
        return
    
    # Verificar se já tem batalha no canal
    if str(ctx.channel.id) in batalhas_galo:
        await ctx.send('❌ Já existe uma batalha neste canal! Aguarde terminar.')
        return
    
    # Buscar galo do desafiante
    cursor.execute('SELECT * FROM galos WHERE id = ? AND user_id = ?', (galo_id, str(ctx.author.id)))
    galo_desafiante = cursor.fetchone()
    
    if not galo_desafiante:
        await ctx.send('❌ Galo não encontrado! Use `.vergalo` para ver seus galos.')
        return
    
    # Buscar principal galo do oponente
    cursor.execute('SELECT * FROM galos WHERE user_id = ? AND is_principal = 1', (str(oponente.id),))
    galo_desafiado = cursor.fetchone()
    
    if not galo_desafiado:
        cursor.execute('SELECT * FROM galos WHERE user_id = ? LIMIT 1', (str(oponente.id),))
        galo_desafiado = cursor.fetchone()
    
    if not galo_desafiado:
        await ctx.send(f'❌ {oponente.mention} não tem galos para batalhar!')
        return
    
    # Criar batalha
    batalha_id = len(batalhas_galo) + 1
    batalhas_galo[str(ctx.channel.id)] = {
        'id': batalha_id,
        'desafiante': ctx.author.id,
        'desafiado': oponente.id,
        'galo_desafiante': galo_desafiante,
        'galo_desafiado': galo_desafiado,
        'turno': ctx.author.id,
        'status': 'aguardando',
        'hp_desafiante': galo_desafiante[7],
        'hp_desafiado': galo_desafiado[7]
    }
    
    embed = Embed(
        title='🐔 BATALHA DE GALOS!',
        description=f'{ctx.author.mention} está desafiando {oponente.mention}!',
        color=Color.orange()
    )
    embed.add_field(name='⚔️ Desafiante', value=f'Galo: {galo_desafiante[2]} (Nível {galo_desafiante[3]})', inline=True)
    embed.add_field(name='🛡️ Desafiado', value=f'Galo: {galo_desafiado[2]} (Nível {galo_desafiado[3]})', inline=True)
    embed.add_field(name='📊 Poder', value=f'{calcular_poder_galo(galo_desafiante[3], galo_desafiante[4], galo_desafiante[5], galo_desafiante[6], galo_desafiante[7])} vs {calcular_poder_galo(galo_desafiado[3], galo_desafiado[4], galo_desafiado[5], galo_desafiado[6], galo_desafiado[7])}', inline=True)
    embed.add_field(name='📝 Status', value='Aguardando oponente aceitar...', inline=False)
    embed.set_footer(text=f'{oponente.mention}, use .aceitar {batalha_id} para começar a batalha!')
    await ctx.send(embed=embed)

@bot.command(name='aceitar')
async def aceitar_batalha(ctx, batalha_id: int = None):
    """Aceita uma batalha de galos"""
    if batalha_id is None:
        await ctx.send(f'❌ Use: `{PREFIXO}aceitar ID_da_batalha`')
        return
    
    # Procurar batalha
    batalha_channel = None
    for channel_id, batalha in batalhas_galo.items():
        if batalha['id'] == batalha_id and batalha['desafiado'] == ctx.author.id and batalha['status'] == 'aguardando':
            batalha_channel = channel_id
            break
    
    if not batalha_channel:
        await ctx.send('❌ Batalha não encontrada ou já iniciada!')
        return
    
    batalha = batalhas_galo[batalha_channel]
    batalha['status'] = 'ativo'
    
    embed = Embed(
        title='🐔 BATALHA INICIADA!',
        description=f'A batalha entre {bot.get_user(batalha["desafiante"]).mention} e {ctx.author.mention} começou!',
        color=Color.green()
    )
    
    # Mostrar status inicial
    galo1 = batalha['galo_desafiante']
    galo2 = batalha['galo_desafiado']
    
    embed.add_field(name=f'⚔️ {galo1[2]}', value=f'❤️ HP: {galo1[7]}/{galo1[7]}\n⚡ Nível: {galo1[3]}', inline=True)
    embed.add_field(name=f'🛡️ {galo2[2]}', value=f'❤️ HP: {galo2[7]}/{galo2[7]}\n⚡ Nível: {galo2[3]}', inline=True)
    embed.add_field(name='🎯 Vez', value=f'{bot.get_user(batalha["desafiante"]).mention}', inline=False)
    embed.set_footer(text='Use .atacar para atacar o oponente!')
    
    await ctx.send(embed=embed)

@bot.command(name='atacar')
async def atacar_galo(ctx):
    """Ataca o oponente na batalha"""
    if str(ctx.channel.id) not in batalhas_galo:
        await ctx.send('❌ Não há batalha ativa neste canal!')
        return
    
    batalha = batalhas_galo[str(ctx.channel.id)]
    
    if batalha['status'] != 'ativo':
        await ctx.send('❌ A batalha não está ativa!')
        return
    
    if ctx.author.id != batalha['turno']:
        await ctx.send('❌ Não é sua vez! Aguarde o oponente atacar.')
        return
    
    # Determinar atacante e defensor
    if ctx.author.id == batalha['desafiante']:
        atacante = batalha['galo_desafiante']
        defensor = batalha['galo_desafiado']
        is_desafiante = True
    else:
        atacante = batalha['galo_desafiado']
        defensor = batalha['galo_desafiante']
        is_desafiante = False
    
    # Calcular ataque
    atacante_stats = {
        'ataque': atacante[4],
        'defesa': defensor[5]
    }
    
    dano = calcular_dano({'ataque': atacante[4]}, {'defesa': defensor[5]})
    
    # Reduzir HP do defensor
    if is_desafiante:
        batalha['hp_desafiado'] -= dano
        hp_atual_def = batalha['hp_desafiado']
        hp_max_def = defensor[7]
    else:
        batalha['hp_desafiante'] -= dano
        hp_atual_def = batalha['hp_desafiante']
        hp_max_def = defensor[7]
    
    embed = Embed(
        title='⚔️ ATAQUE!',
        description=f'{ctx.author.mention} atacou com {atacante[2]}!',
        color=Color.red()
    )
    embed.add_field(name='💥 Dano', value=f'{dano} de dano!', inline=True)
    
    # Verificar se derrotou
    if hp_atual_def <= 0:
        vencedor = ctx.author
        perdedor_id = batalha['desafiado'] if is_desafiante else batalha['desafiante']
        perdedor = bot.get_user(perdedor_id)
        
        # Atualizar estatísticas
        cursor.execute('UPDATE galos SET vitorias = vitorias + 1 WHERE id = ?', (atacante[0],))
        cursor.execute('UPDATE galos SET derrotas = derrotas + 1 WHERE id = ?', (defensor[0],))
        
        # Ganhar experiência (50 XP por vitória)
        ganhar_experiencia(atacante[0], 50)
        ganhar_experiencia(defensor[0], 25)
        
        # Ganhar recompensa (R$ 10 por vitória)
        add_saldo(str(vencedor.id), 10)
        
        embed.add_field(name='🏆 VITÓRIA!', value=f'{vencedor.mention} venceu a batalha com {atacante[2]}!', inline=False)
        embed.add_field(name='💰 Recompensa', value=f'{vencedor.mention} ganhou R$ 10,00!', inline=True)
        embed.add_field(name='⭐ Experiência', value=f'{atacante[2]} ganhou 50 XP!\n{defensor[2]} ganhou 25 XP!', inline=True)
        
        await ctx.send(embed=embed)
        
        # Remover batalha
        del batalhas_galo[str(ctx.channel.id)]
        return
    
    # Mudar turno
    batalha['turno'] = batalha['desafiado'] if is_desafiante else batalha['desafiante']
    
    # Mostrar status atualizado
    embed.add_field(name='📊 Status Atual', value=f'''
    ⚔️ **{batalha['galo_desafiante'][2]}:** ❤️ {batalha['hp_desafiante']}/{batalha['galo_desafiante'][7]} HP
    🛡️ **{batalha['galo_desafiado'][2]}:** ❤️ {batalha['hp_desafiado']}/{batalha['galo_desafiado'][7]} HP
    ''', inline=False)
    embed.add_field(name='🎯 Próximo turno', value=f'{bot.get_user(batalha["turno"]).mention}', inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='lojagalo')
async def loja_galo(ctx):
    """Mostra a loja de itens para galos"""
    cursor.execute('SELECT * FROM loja_galo ORDER BY valor')
    itens = cursor.fetchall()
    
    embed = Embed(
        title='🛒 Loja de Melhorias para Galos',
        description=f'Use `{PREFIXO}comprar ITEM_ID` para comprar um item',
        color=Color.blue()
    )
    
    for item in itens:
        embed.add_field(
            name=f'{item[1]} - R$ {item[3]}',
            value=f'📦 Tipo: {item[2]}\n✨ {item[8]}\n🔧 Bônus: +{item[4]} Ataque, +{item[5]} Defesa, +{item[6]} Velocidade, +{item[7]} HP',
            inline=False
        )
    
    embed.set_footer(text='Use .inventario para ver seus itens')
    await ctx.send(embed=embed)

@bot.command(name='comprar')
async def comprar_item(ctx, item_id: int, galo_id: int = None):
    """Compra um item da loja para seu galo"""
    cursor.execute('SELECT * FROM loja_galo WHERE id = ?', (item_id,))
    item = cursor.fetchone()
    
    if not item:
        await ctx.send('❌ Item não encontrado!')
        return
    
    if galo_id is None:
        await ctx.send(f'❌ Use: `{PREFIXO}comprar ID_do_item ID_do_galo`\nUse `.vergalo` para ver seus galos')
        return
    
    cursor.execute('SELECT * FROM galos WHERE id = ? AND user_id = ?', (galo_id, str(ctx.author.id)))
    galo = cursor.fetchone()
    
    if not galo:
        await ctx.send('❌ Galo não encontrado!')
        return
    
    saldo_atual = get_saldo(str(ctx.author.id))
    
    if saldo_atual < item[3]:
        await ctx.send(f'❌ Saldo insuficiente! Você precisa de R$ {item[3]}')
        return
    
    # Aplicar bônus ao galo
    cursor.execute('''
    UPDATE galos 
    SET ataque = ataque + ?,
        defesa = defesa + ?,
        velocidade = velocidade + ?,
        hp = hp + ?,
        hp_atual = hp_atual + ?
    WHERE id = ?
    ''', (item[4], item[5], item[6], item[7], item[7], galo_id))
    
    # Descontar saldo
    add_saldo(str(ctx.author.id), -item[3])
    conn.commit()
    
    embed = Embed(
        title='🛒 Compra Realizada!',
        description=f'Você comprou **{item[1]}** para seu galo {galo[2]}!',
        color=Color.green()
    )
    embed.add_field(name='💰 Saldo gasto', value=f'R$ {item[3]:.2f}', inline=True)
    embed.add_field(name='📊 Saldo restante', value=f'R$ {get_saldo(str(ctx.author.id)):.2f}', inline=True)
    embed.add_field(name='✨ Bônus aplicados', value=f'⚔️ +{item[4]} Ataque\n🛡️ +{item[5]} Defesa\n⚡ +{item[6]} Velocidade\n❤️ +{item[7]} HP', inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='rankinggalos')
async def ranking_galos(ctx):
    """Mostra o ranking dos galos mais fortes"""
    cursor.execute('''
    SELECT g.nome_galo, g.nivel, g.vitorias, u.username 
    FROM galos g
    JOIN users u ON g.user_id = u.id
    ORDER BY g.nivel DESC, g.vitorias DESC
    LIMIT 10
    ''')
    
    # Como não temos tabela users, vamos usar outro método
    cursor.execute('''
    SELECT nome_galo, nivel, vitorias, user_id 
    FROM galos 
    ORDER BY nivel DESC, vitorias DESC 
    LIMIT 10
    ''')
    galos = cursor.fetchall()
    
    embed = Embed(title='🏆 Ranking dos Galos Mais Fortes', description='Os guerreiros mais poderosos do servidor!', color=Color.gold())
    
    for i, galo in enumerate(galos, 1):
        user = bot.get_user(int(galo[3]))
        nome_user = user.display_name if user else "Usuário Desconhecido"
        embed.add_field(
            name=f'{i}º - {galo[0]}',
            value=f'👤 Dono: {nome_user}\n🎯 Nível: {galo[1]} | 🏆 Vitórias: {galo[2]}',
            inline=False
        )
    
    await ctx.send(embed=embed)

async def gerar_imagem_galo(galo_id, nome, nivel):
    """Gera uma imagem personalizada do galo baseado no nível"""
    # URLs de imagens por nível
    if nivel <= 10:
        url = "https://cdn-icons-png.flaticon.com/512/1995/1995572.png"  # Galo básico
    elif nivel <= 30:
        url = "https://cdn-icons-png.flaticon.com/512/1995/1995584.png"  # Galo guerreiro
    elif nivel <= 60:
        url = "https://cdn-icons-png.flaticon.com/512/1995/1995596.png"  # Galo cavaleiro
    elif nivel <= 100:
        url = "https://cdn-icons-png.flaticon.com/512/1995/1995599.png"  # Galo lorde
    else:
        url = "https://cdn-icons-png.flaticon.com/512/1995/1995600.png"  # Galo lendário
    
    return url

# ========== FUNÇÕES EXISTENTES (moderação, saldo, etc) ==========
# [Todas as funções anteriores do bot continuam aqui...]

# ========== EVENTOS ==========

@bot.event
async def on_ready():
    print(f'✅ Bot {bot.user.name} está online!')
    print(f'📝 Prefixo: {PREFIXO}')
    print(f'📊 Servidores: {len(bot.guilds)}')
    print(f'👑 Donos autorizados: {DONOS_IDS}')
    print(f'🐔 Sistema de Briga de Galo ativado!')
    await bot.change_presence(activity=discord.Game(name=f'{PREFIXO}ajuda | {len(bot.guilds)} servidores'))

# [Restante do código existente continua...]

# Rodar bot
if __name__ == '__main__':
    if TOKEN == 'SEU_TOKEN_AQUI':
        print('❌ Por favor, coloque o TOKEN do seu bot no arquivo bot.py!')
        print('Edite a linha TOKEN = "SEU_TOKEN_AQUI" e coloque seu token')
    else:
        bot.run(TOKEN)