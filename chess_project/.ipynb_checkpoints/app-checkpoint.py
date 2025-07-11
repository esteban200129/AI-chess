from flask import Flask, render_template, jsonify
import chess
import chess.svg

app = Flask(__name__)

# 初始化遊戲邏輯
class ChessGame:
    def __init__(self):
        self.board = chess.Board()

    def get_board_svg(self):
        # 返回棋盤的 SVG 格式
        return chess.svg.board(self.board)

    def move_piece(self, move):
        # 執行一個棋步，並返回成功與否
        try:
            self.board.push_san(move)
            return True
        except ValueError:
            return False

    def reset_game(self):
        # 重置棋局
        self.board = chess.Board()

game = ChessGame()  # 創建棋局實例

@app.route('/')
def index():
    # 返回當前棋盤的 SVG
    board_svg = game.get_board_svg()
    return render_template("index.html", board=board_svg)

@app.route('/move/<move>')
def move(move):
    # 嘗試執行棋步
    if game.move_piece(move):
        board_svg = game.get_board_svg()
        return jsonify(board=board_svg)
    else:
        return jsonify(message="Invalid move"), 400

@app.route('/reset')
def reset_game():
    # 重置棋局
    game.reset_game()
    board_svg = game.get_board_svg()
    return jsonify(board=board_svg)

if __name__ == "__main__":
    app.run(debug=True, port=8000)