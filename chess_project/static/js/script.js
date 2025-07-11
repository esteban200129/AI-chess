document.addEventListener("DOMContentLoaded", function () {
    const chessBoard = document.getElementById("chess-board");
    const undoButton = document.getElementById("undo-button");
    const aiMoveButton = document.getElementById("ai-move-button");
    const resetButton = document.getElementById("reset-button");
    const gameStatus = document.getElementById("game-status");
    const moveList = document.getElementById("move-list");
    const recommendedMovesContainer = document.getElementById("recommended-moves");
    let selectedSquare = null;

    const pieces = {
        "r": "♜", "n": "♞", "b": "♝", "q": "♛", "k": "♚", "p": "♟",
        "R": "♖", "N": "♘", "B": "♗", "Q": "♕", "K": "♔", "P": "♙"
    };

    function indexToSquare(index) {
        const file = "abcdefgh"[index % 8];
        const rank = 8 - Math.floor(index / 8);
        return file + rank;
    }

    function initializeBoard(pgn = "") {
        chessBoard.innerHTML = ""; // 清空棋盤
        fetch("/get_board_state", { 
            method: "POST", 
            headers: { "Content-Type": "application/json" }, 
            body: JSON.stringify({ pgn }) 
        })
        .then(response => response.json())
        .then(boardState => {
            boardState.forEach((row, rank) => {
                row.forEach((piece, file) => {
                    const squareId = rank * 8 + file;
                    createSquare(squareId, piece ? pieces[piece] : null);
                });
            });
        })
        .catch(error => console.error("Error initializing board:", error));
    }

    function createSquare(id, piece) {
        const square = document.createElement("div");
        square.classList.add("chess-square");
        square.id = id;
        square.innerHTML = piece ? `<span>${piece}</span>` : "";
        square.addEventListener("click", () => handleSquareClick(square));
        chessBoard.appendChild(square);
    }

    function handleSquareClick(square) {
        if (!selectedSquare && square.innerHTML) {
            selectedSquare = square;
            square.style.border = "2px solid blue";
        } else if (selectedSquare) {
            const from = indexToSquare(parseInt(selectedSquare.id));
            const to = indexToSquare(parseInt(square.id));
            movePiece(from, to);
            selectedSquare.style.border = "";
            selectedSquare = null;
        }
    }

    function movePiece(from, to) {
        const piece = selectedSquare.innerText;
        let promotion = "";
    
        if ((piece === "♙" && from[1] === "7") || (piece === "♟" && from[1] === "2")) {
            promotion = prompt("兵升變！請輸入 'q' (皇后), 'r' (城堡), 'b' (主教), 'n' (騎士):", "q");
        }
    
        fetch("/move", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: `from=${from}&to=${to}&promotion=${promotion}`
        })
            .then(response => response.json())
            .then(data => {
                console.log("Move Response:", data); // 打印完整的返回數據
                if (data.status === "success") {
                    initializeBoard();
                    updateMoveList(data.move_stack);
                    document.getElementById("opening-name").innerText = `Current Opening: ${data.opening_name || "Unknown"}`;
                    document.getElementById("last-move").innerText = `Last Move: ${data.last_move || "None"}`;
                    updateGameStatus(data.game_status);
    
                    // 更新推薦和可能的開局
                    displayRecommendations(data.recommendations);
                    displayPossibleOpenings(data.possible_openings);
                } else {
                    alert(`錯誤！${data.message}`);
                }
            })
            .catch(error => {
                console.error("Error during movePiece:", error);
                alert("出現未知錯誤，請稍後再試！");
            });
    }

    function updateGameInfo(data) {
        document.getElementById("opening-name").innerText = `Current Opening: ${data.opening_name || "Unknown"}`;
        document.getElementById("last-move").innerText = `Last Move: ${data.last_move || "None"}`;
        updateGameStatus(data.game_status);
        displayRecommendations(data.recommendations);
    }

    function updateGameStatus(status) {
        const statusText = {
            checkmate: "Checkmate!",
            check: "Check!",
            stalemate: "Stalemate!",
            draw: "Draw!",
            ongoing: "Game is ongoing"
        };
        gameStatus.innerText = statusText[status] || "Unknown status";
    }

    function updateMoveList(pgnMoves) {
        moveList.innerHTML = ""; // 清空舊棋譜
        pgnMoves.forEach(line => {
            const moveElement = document.createElement("div");
            moveElement.textContent = line.trim(); // 顯示 PGN 每一行
            moveList.appendChild(moveElement);
        });
    }

    function displayRecommendations(recommendations) {
        const recommendedMoves = document.getElementById("recommended-moves");
        if (recommendations && recommendations.length > 0) {
            // 按來源分組，構建顯示內容
            const groupedBySource = recommendations.reduce((acc, rec) => {
                const source = rec.Source || "Unknown Source";
                if (!acc[source]) {
                    acc[source] = [];
                }
                acc[source].push(`${rec.Move || "N/A"}: ${rec["Probability%"] || "N/A"}`);
                return acc;
            }, {});
    
            // 渲染分組內容
            recommendedMoves.innerHTML = Object.entries(groupedBySource)
                .map(([source, moves]) => `
                    <div>
                        <strong>${source}:</strong>
                        <ul>
                            ${moves.map(move => `<li>${move}</li>`).join("")}
                        </ul>
                    </div>
                `).join("<hr>"); // 每個來源之間用水平線分隔
        } else {
            recommendedMoves.innerHTML = "<p>No recommended moves available.</p>";
        }
    }

    function fetchPossibleOpenings(pgn) {
        fetch("/get_possible_openings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pgn: pgn })
        })
            .then(response => response.json())
            .then(data => {
                if (data.status === "success") {
                    displayPossibleOpenings(data.possible_openings);
                } else {
                    console.error("Error fetching possible openings:", data.message);
                }
            })
            .catch(error => {
                console.error("Error in fetchPossibleOpenings:", error);
            });
    }
    
    function displayPossibleOpenings(openings) {
        const openingsList = document.getElementById("openings-list");
        openingsList.innerHTML = ""; // 清空現有列表
    
        if (openings && openings.length > 0) {
            // 隨機打亂開局列表
            const shuffledOpenings = openings.sort(() => Math.random() - 0.5);
    
            // 限制顯示數量至最多 10 個
            const limitedOpenings = shuffledOpenings.slice(0, 10);
    
            // 分兩列顯示，準備列容器
            const column1 = document.createElement("div");
            const column2 = document.createElement("div");
            column1.classList.add("openings-column");
            column2.classList.add("openings-column");
    
            // 將開局按順序分配到兩列
            limitedOpenings.forEach((opening, index) => {
                const listItem = document.createElement("div");
                listItem.innerHTML = `
                    <strong>${opening.name}</strong>: ${opening.full_line}
                `;
                if (index % 2 === 0) {
                    column1.appendChild(listItem); // 分配到第一列
                } else {
                    column2.appendChild(listItem); // 分配到第二列
                }
            });
    
            // 添加列到主列表容器
            openingsList.appendChild(column1);
            openingsList.appendChild(column2);
        } else {
            openingsList.innerHTML = "<p>No possible openings found.</p>";
        }
    }

    resetButton.addEventListener("click", () => {
        fetch("/reset", { method: "POST" })
            .then(response => response.json())
            .then(data => {
                if (data.status === "success") {
                    initializeBoard();
                    updateMoveList([]);
                    gameStatus.innerText = "Game has been reset";
                } else {
                    alert("Failed to reset the board");
                }
            })
            .catch(error => console.error("Error resetting board:", error));
    });

    undoButton.addEventListener("click", () => {
        fetch("/undo", { method: "POST" })
            .then(response => response.json())
            .then(data => {
                initializeBoard();
                updateMoveList(data.move_stack || []);
            })
            .catch(error => console.error("Error undoing move:", error));
    });

    aiMoveButton.addEventListener("click", () => {
        fetch("/ai_move", { method: "POST" })
            .then(response => response.json())
            .then(data => {
                if (data.status === "success") {
                    initializeBoard();
                    updateMoveList(data.move_stack || []);
                } else {
                    alert("AI Move Failed");
                }
            })
            .catch(error => console.error("Error during AI move:", error));
    });

    // 初始化遊戲
    initializeBoard([]);
});