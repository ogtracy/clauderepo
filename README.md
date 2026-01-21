# Classic Board Games

Two command-line board games where you can play against a computer opponent.

## Games Included

### 1. Tic-Tac-Toe (`tictactoe.py`)

A classic 3x3 grid game where you try to get 3 in a row.

**Features:**
- Human vs Computer gameplay
- Smart AI opponent that:
  - Tries to win when possible
  - Blocks your winning moves
  - Prefers strategic positions (center and corners)
- Clear visual board display
- Input validation

**How to Play:**

1. Run the game:
   ```bash
   python3 tictactoe.py
   ```

2. Enter your move by typing a number from 0-8 corresponding to the board position:
   ```
   | 0 | 1 | 2 |
   | 3 | 4 | 5 |
   | 6 | 7 | 8 |
   ```

3. You play as X, computer plays as O
4. First player to get 3 in a row (horizontal, vertical, or diagonal) wins!

### 2. Connect 4 (`connect4.py`)

A classic vertical strategy game played on a 6x7 grid where you try to get 4 pieces in a row.

**Features:**
- Human vs Computer gameplay
- Advanced AI opponent that:
  - Tries to win when possible
  - Blocks your winning moves
  - Creates multiple winning opportunities
  - Prefers center and strategic columns
- Realistic gravity mechanics (pieces fall to bottom)
- Clear visual board display with column numbers
- Full/invalid move detection

**How to Play:**

1. Run the game:
   ```bash
   python3 connect4.py
   ```

2. Enter your move by typing a column number (0-6):
   ```
     0   1   2   3   4   5   6
   +---+---+---+---+---+---+---+
   |   |   |   |   |   |   |   |
   +---+---+---+---+---+---+---+
   ```

3. You play as Red (R), computer plays as Yellow (Y)
4. Pieces drop down due to gravity to the lowest available position
5. First player to get 4 in a row (horizontal, vertical, or diagonal) wins!

## Bug Fix (Tic-Tac-Toe)

Fixed a critical bug in the `find_winning_move` method where a comparison operator (`==`) was incorrectly used instead of an assignment operator (`=`) on line 141. This prevented the AI from properly simulating moves to find winning positions or block the opponent.

**Before (buggy):**
```python
test_board[move] == letter  # Comparison, doesn't modify the board
```

**After (fixed):**
```python
test_board[move] = letter  # Assignment, properly simulates the move
```

This is a common error-prone pattern where developers accidentally use `==` when they mean `=`.
