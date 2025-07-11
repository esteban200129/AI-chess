from flask import Flask, render_template, request, jsonify
import chess
import chess.pgn
import chess.engine
import io
import json
import logging

app = Flask(__name__)

# 初始化棋盤管理器
class ChessBoardManager:
    def __init__(self):
        self.board = chess.Board()  # 初始化棋盤

    def push_move(self, move_uci):
        """執行棋子的移動"""
        move = chess.Move.from_uci(move_uci)
        if move in self.board.legal_moves:
            self.board.push(move)
            return True, self.board
        else:
            # 修改錯誤訊息，只返回簡短提示
            return False, f"Move {move_uci} is not legal."
    def undo_move(self):
        """撤銷最後一步棋"""
        if len(self.board.move_stack) > 0:
            last_move = self.board.pop()
            return True, f"Undo move: {last_move.uci()}"
        return False, "No move to undo."

    def reset_board(self):
        """重置棋盤到初始狀態"""
        self.board.reset()

    def generate_lan(self):
        """生成最後一步的具體座標（LAN 格式）"""
        try:
            if len(self.board.move_stack) == 0:
                return "No last move"

            last_move = self.board.peek()  # 獲取最後一步
            return f"{chess.square_name(last_move.from_square)} {chess.square_name(last_move.to_square)}"
        except Exception as e:
            print(f"Error in generating LAN: {e}")
            return f"Error generating LAN: {e}"

    def get_board_state(self):
        ranks = []
        for rank in range(8):
            row = []
            for file in range(8):
                square = chess.square(file, 7 - rank)
                piece = self.board.piece_at(square)
                row.append(piece.symbol() if piece else None)
            ranks.append(row)
        return ranks

# 初始化 PGN 管理器
class PGNManager:
    def __init__(self, board):
        self.board = board

    def update_pgn(self):
        try:
            game = chess.pgn.Game()
            node = game
            temp_board = chess.Board()
            for move in self.board.move_stack:
                if move not in temp_board.legal_moves:
                    return "", f"Illegal move detected: {move.uci()}"
                temp_board.push(move)
                node = node.add_main_variation(move)
            exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
            return game.accept(exporter), None
        except Exception as e:
            return "", f"Error in update_pgn: {e}"

# 初始化開局匹配器

# 設置日誌格式和級別
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class OpeningMatcher:
    def __init__(self, openings):
        self.openings = openings

    def match_opening(self, pgn):
        """改進匹配開局名稱，支持進展更新"""
        try:
            # 簡化輸出
            steps_only = clean_pgn(pgn)
            logging.info(f"Matching opening for input PGN: {steps_only[:20]}...")  # 打印簡短信息

            matched_opening = None
            matched_length = 0
            for opening in self.openings:
                opening_pgn_standardized = clean_pgn(opening["pgn"])
                if steps_only.startswith(opening_pgn_standardized) and len(opening_pgn_standardized) > matched_length:
                    matched_opening = opening["name"]
                    matched_length = len(opening_pgn_standardized)

            if matched_opening:
                logging.info(f"Matched opening: {matched_opening}")  # 打印匹配結果
                return matched_opening

            logging.info("No matching opening found.")
            return "Unknown"
        except Exception as e:
            logging.error(f"Error in match_opening: {e}")
            return f"Error in match_opening: {e}"

# 初始化模組
chess_manager = ChessBoardManager()
pgn_manager = PGNManager(chess_manager.board)
with open("chess_project/data/raw/openings.json", "r") as f:
    openings_data = json.load(f)
opening_matcher = OpeningMatcher(openings_data)
# 載入推薦數據
with open("chess_project/data/processed/sequence_recommendations.json", "r") as f:
    sequence_recommendations = json.load(f)

def clean_pgn(pgn):
    """
    清理 PGN，生成固定格式 "1.e4 e5 2.Nf3 Nc6 3.Bb5"。
    """
    steps = []
    for line in pgn.splitlines():
        if line and not line.startswith('['):  # 排除 PGN 的標頭信息
            # 去除多餘空格，確保步與步之間的間隔統一
            cleaned_line = line.strip()
            steps.append(cleaned_line)
    # 把步數拼接成單行，保證數字點後無空格，步數之間有空格
    cleaned_pgn = " ".join(steps).replace(" *", "").replace(". ", ".")
    return cleaned_pgn

def get_possible_openings(pgn):
    """
    根據當前 PGN 匹配所有可能的開局，並限制輸出的數據量。
    """
    matched_openings = []
    try:
        # 清理 PGN
        cleaned_pgn = clean_pgn(pgn)

        # 僅打印簡短信息：匹配到的總數
        logging.info(f"Matching PGN: {cleaned_pgn[:20]}...")  # 打印簡短 PGN

        for opening in openings_data:
            opening_pgn = clean_pgn(opening["pgn"])
            if opening_pgn.startswith(cleaned_pgn) or cleaned_pgn.startswith(opening_pgn):
                matched_openings.append({
                    "name": opening["name"],
                    "full_line": opening["pgn"]
                })

        # 僅打印匹配總數，省略具體條目
        logging.info(f"Found {len(matched_openings)} possible openings.")  # 只打印總數
        return matched_openings[:10]  # 只返回最多 10 條數據
    except Exception as e:
        logging.error(f"Error in get_possible_openings: {e}")
        return []

def recommend_moves(pgn, board):
    """
    根據完整的 PGN 鍵值推薦下一步棋。
    優先順序：
    1. 從 sequence_recommendations.json 匹配 (Bobby 的歷史比賽數據)。
    2. 根據 Bobby 的棋風特徵模擬 (模擬數據)。
    3. 使用 Stockfish 引擎生成推薦。
    """
    try:
        # Step 1: 清理 PGN
        cleaned_pgn = clean_pgn(pgn)
        print(f"Cleaned PGN for recommendations: {cleaned_pgn}")
        
        # Step 2: 匹配 sequence_recommendations.json
        recommendations = sequence_recommendations.get(cleaned_pgn, [])
        if recommendations:
            print("Matched sequence_recommendations.json")
            # 添加來源標記
            for rec in recommendations:
                rec["Source"] = "Bobby's Historical Data"
            recommendations.sort(key=lambda x: -float(x["Probability%"].strip('%')))
            return recommendations
        
        # Step 3: 模擬 Bobby 棋風（若無匹配序列）
        bobby_style_recommendations = recommend_bobby_style(board)
        if bobby_style_recommendations:
            print("Generated Bobby-style recommendations")
            # 添加來源標記
            for rec in bobby_style_recommendations:
                rec["Source"] = "Bobby's Style Simulation"
            return bobby_style_recommendations

        # Step 4: 使用 Stockfish 引擎（最後選項）
        engine_recommendations = recommend_stockfish(board)
        print("Generated recommendations from Stockfish")
        # 添加來源標記
        for rec in engine_recommendations:
            rec["Source"] = "Stockfish Recommendation"
        return engine_recommendations
    
    except Exception as e:
        print(f"Error during recommendations: {e}")
        return []
    
def recommend_bobby_style(board):
    """
    模擬 Bobby 棋風，根據棋盤特徵推薦下一步棋。
    偏向中心控制、開放線等策略，並給出模擬概率。
    """
    recommendations = []
    try:
        # 獲取所有合法移動
        legal_moves = list(board.legal_moves)
        
        # 定義中心控制的重要位置
        center_squares = [chess.E4, chess.D4, chess.E5, chess.D5]
        center_control_moves = []
        open_file_moves = []
        
        for move in legal_moves:
            if move.to_square in center_squares:
                center_control_moves.append(move)
            else:
                open_file_moves.append(move)

        # 設置模擬的概率分布
        total_moves = len(center_control_moves) + len(open_file_moves)
        if total_moves == 0:
            return []

        # 假設中心控制步數佔 70% 的概率
        for move in center_control_moves:
            recommendations.append({
                "Move": board.san(move),
                "Reason": "Center control",
                "Probability%": f"{(0.7 / len(center_control_moves) * 100):.2f}%"
            })
        
        # 假設開放線策略佔 30% 的概率
        for move in open_file_moves:
            recommendations.append({
                "Move": board.san(move),
                "Reason": "Open file strategy",
                "Probability%": f"{(0.3 / len(open_file_moves) * 100):.2f}%"
            })

        # 按概率排序
        recommendations.sort(key=lambda x: -float(x["Probability%"].strip('%')))
        return recommendations[:5]  # 返回最多 5 條推薦
    except Exception as e:
        print(f"Error in Bobby-style recommendations: {e}")
        return []
    
def recommend_stockfish(board):
    """
    使用 Stockfish 引擎生成推薦，並根據評估分數生成概率。
    """
    recommendations = []
    try:
        with chess.engine.SimpleEngine.popen_uci(ENGINE_PATH) as engine:
            # 讓引擎計算最多 5 個變體
            info = engine.analyse(board, chess.engine.Limit(time=0.5), multipv=5)
            total_score = 0
            move_scores = []

            # 收集每個變體的分數
            for key in info:
                move = key.get("pv")[0]  # 每個變體的第一步
                score = key.get("score").relative.score(mate_score=10000)  # 引擎的評分
                move_scores.append((move, score))
                total_score += max(score, 1)  # 確保不為 0

            # 計算每個步數的概率
            for move, score in move_scores:
                probability = (score / total_score) * 100
                recommendations.append({
                    "Move": board.san(move),
                    "Reason": "Stockfish recommendation",
                    "Probability%": f"{probability:.2f}%"
                })

        recommendations.sort(key=lambda x: -float(x["Probability%"].strip('%')))
        return recommendations
    except Exception as e:
        print(f"Error in Stockfish recommendations: {e}")
        return []

ENGINE_PATH = "stockfish"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/move', methods=['POST'])
def move():
    from_square = request.form['from']
    to_square = request.form['to']
    promotion = request.form.get('promotion', None)

    move_uci = f"{from_square}{to_square}{promotion if promotion else ''}"
    success, result = chess_manager.push_move(move_uci)

    if success:
        # 更新 PGN 並匹配開局
        pgn, error = pgn_manager.update_pgn()
        if error:
            return jsonify({'status': 'error', 'message': error})

        last_move_lan = chess_manager.generate_lan()
        opening_name = opening_matcher.match_opening(pgn)

        # 推薦下一步棋
        recommendations = recommend_moves(pgn, chess_manager.board)
        
        # 獲取可能的開局
        possible_openings = get_possible_openings(pgn)

        response = {
            'status': 'success',
            'move_stack': [line for line in pgn.splitlines() if not line.startswith('[')],
            'opening_name': opening_name,
            'last_move': last_move_lan,
            'game_status': check_game_status(),
            'recommendations': recommendations[:5],  # 返回前 5 條推薦
            'cleaned_pgn': clean_pgn(pgn),  # 返回清理後的 PGN 供調試
            'possible_openings': possible_openings
        }

        # 簡化打印
        logging.info(f"Move executed. Opening: {opening_name}, Recommendations: {len(recommendations)}")
        return jsonify(response)
    else:
        return jsonify({'status': 'invalid move', 'message': result})


@app.route('/undo', methods=['POST'])
def undo():
    success, result = chess_manager.undo_move()
    if success:
        pgn, error = pgn_manager.update_pgn()
        if error:
            return jsonify({'status': 'error', 'message': error})

        opening_name = opening_matcher.match_opening(pgn)
        return jsonify({
            'status': 'success',
            'move_stack': [line for line in pgn.splitlines() if not line.startswith('[')],
            'opening_name': opening_name,
            'game_status': check_game_status()
        })
    else:
        return jsonify({'status': 'error', 'message': result})

@app.route('/ai_move', methods=['POST'])
def ai_move():
    try:
        # 檢查引擎路徑
        print(f"Using engine path: {ENGINE_PATH}")

        # 使用 chess.engine 啟動 Stockfish 引擎
        with chess.engine.SimpleEngine.popen_uci(ENGINE_PATH) as engine:
            print("Engine started successfully.")

            # 根據當前棋盤狀態，讓 AI 計算最佳走法
            result = engine.play(chess_manager.board, chess.engine.Limit(time=0.1))
            print(f"AI move generated: {result.move}")

            # 推進 AI 的移動到棋盤
            chess_manager.board.push(result.move)

        # 更新 PGN 並匹配開局
        pgn, error = pgn_manager.update_pgn()
        if error:
            return jsonify({'status': 'error', 'message': error})

        last_move_lan = chess_manager.generate_lan()
        opening_name = opening_matcher.match_opening(pgn)

        return jsonify({
            'status': 'success',
            'move_stack': [line for line in pgn.splitlines() if not line.startswith('[')],
            'opening_name': opening_name,
            'last_move': last_move_lan,
            'game_status': check_game_status()
        })

    except chess.engine.EngineTerminatedError:
        return jsonify({'status': 'error', 'message': 'AI engine terminated unexpectedly. Check your engine path.'})

    except chess.engine.EngineError as e:
        return jsonify({'status': 'error', 'message': f'Engine error: {e}'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Unexpected error: {e}'})

@app.route('/reset', methods=['POST'])
def reset():
    chess_manager.reset_board()
    return jsonify({
        'status': 'success',
        'move_stack': [],
        'opening_name': "Unknown",
        'game_status': 'ongoing'
    })

@app.route('/get_board_state', methods=['POST'])
def get_board_state():
    return jsonify(chess_manager.get_board_state())

def check_game_status():
    if chess_manager.board.is_checkmate():
        return "checkmate"
    elif chess_manager.board.is_check():
        return "check"
    elif chess_manager.board.is_stalemate():
        return "stalemate"
    elif chess_manager.board.is_insufficient_material():
        return "draw"
    else:
        return "ongoing"
    
@app.route('/get_possible_openings', methods=['POST'])
def get_possible_openings_route():
    try:
        pgn = request.json.get('pgn', '')
        possible_openings = get_possible_openings(pgn)
        return jsonify({
            'status': 'success',
            'possible_openings': possible_openings
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    app.run(debug=True, port=8000)