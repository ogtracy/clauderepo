# Tic-Tac-Toe Game

A command-line tic-tac-toe game where you play as X against a computer opponent (O).

## Features

- Human vs Computer gameplay
- Smart AI opponent that:
  - Tries to win when possible
  - Blocks your winning moves
  - Prefers strategic positions (center and corners)
- Clear visual board display
- Input validation

## How to Play

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

## Bug Fix

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
