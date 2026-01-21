#!/usr/bin/env python3
"""
Connect 4 Game
A Connect 4 game where a human player (Red) plays against a computer (Yellow).
"""

import random
import sys


class Connect4:
    def __init__(self, rows=6, cols=7):
        """Initialize the game board and game state."""
        self.rows = rows
        self.cols = cols
        self.board = [[' ' for _ in range(cols)] for _ in range(rows)]
        self.current_winner = None

    def print_board(self):
        """Display the current game board."""
        print("\n")
        # Print column numbers
        print("  " + "   ".join([str(i) for i in range(self.cols)]))
        print("+" + "---+" * self.cols)

        # Print board rows (top to bottom)
        for row in self.board:
            print("| " + " | ".join(row) + " |")
            print("+" + "---+" * self.cols)
        print()

    def available_columns(self):
        """Return a list of columns that are not full."""
        return [col for col in range(self.cols) if self.board[0][col] == ' ']

    def is_full(self):
        """Check if the board is completely full."""
        return len(self.available_columns()) == 0

    def get_next_open_row(self, col):
        """Find the next open row in a column (where piece will fall to)."""
        for row in range(self.rows - 1, -1, -1):
            if self.board[row][col] == ' ':
                return row
        return None

    def make_move(self, col, piece):
        """
        Drop a piece in the specified column.
        Returns True if the move was valid, False otherwise.
        """
        if col not in self.available_columns():
            return False

        row = self.get_next_open_row(col)
        if row is not None:
            self.board[row][col] = piece
            if self.check_winner(row, col, piece):
                self.current_winner = piece
            return True
        return False

    def check_winner(self, row, col, piece):
        """Check if the last move resulted in a win (4 in a row)."""
        # Check horizontal
        count = 0
        for c in range(self.cols):
            if self.board[row][c] == piece:
                count += 1
                if count >= 4:
                    return True
            else:
                count = 0

        # Check vertical
        count = 0
        for r in range(self.rows):
            if self.board[r][col] == piece:
                count += 1
                if count >= 4:
                    return True
            else:
                count = 0

        # Check diagonal (bottom-left to top-right)
        count = 0
        start_row = row - min(row, col)
        start_col = col - min(row, col)
        r, c = start_row, start_col
        while r < self.rows and c < self.cols:
            if self.board[r][c] == piece:
                count += 1
                if count >= 4:
                    return True
            else:
                count = 0
            r += 1
            c += 1

        # Check diagonal (top-left to bottom-right)
        count = 0
        start_row = row + min(self.rows - 1 - row, col)
        start_col = col - min(self.rows - 1 - row, col)
        r, c = start_row, start_col
        while r >= 0 and c < self.cols:
            if self.board[r][c] == piece:
                count += 1
                if count >= 4:
                    return True
            else:
                count = 0
            r -= 1
            c += 1

        return False


class HumanPlayer:
    def __init__(self, piece):
        """Initialize a human player with their piece (R or Y)."""
        self.piece = piece

    def get_move(self, game):
        """Get a valid column choice from the human player."""
        valid_col = False
        col = None
        while not valid_col:
            try:
                col = input(f"{self.piece}'s turn. Enter column (0-{game.cols-1}): ")
                col = int(col)
                if col not in game.available_columns():
                    print(f"Column {col} is full or invalid. Try again.")
                else:
                    valid_col = True
            except (ValueError, KeyboardInterrupt):
                print("Invalid input. Try again.")
        return col


class ComputerPlayer:
    def __init__(self, piece):
        """Initialize a computer player with their piece (R or Y)."""
        self.piece = piece

    def get_move(self, game):
        """Get a move for the computer player using AI strategy."""
        # Try to win first
        col = self.find_winning_move(game, self.piece)
        if col is not None:
            return col

        # Block opponent from winning
        opponent = 'Y' if self.piece == 'R' else 'R'
        col = self.find_winning_move(game, opponent)
        if col is not None:
            return col

        # Look for moves that set up multiple winning opportunities
        col = self.find_strategic_move(game)
        if col is not None:
            return col

        # Prefer center column
        center = game.cols // 2
        if center in game.available_columns():
            return center

        # Prefer columns near center
        available = game.available_columns()
        available.sort(key=lambda x: abs(x - center))
        return available[0]

    def find_winning_move(self, game, piece):
        """Find a column that would result in a win for the given piece."""
        for col in game.available_columns():
            # Simulate the move
            row = game.get_next_open_row(col)
            if row is not None:
                # Temporarily place piece
                game.board[row][col] = piece

                # Check if this wins
                wins = game.check_winner(row, col, piece)

                # Remove piece
                game.board[row][col] = ' '

                if wins:
                    return col
        return None

    def find_strategic_move(self, game):
        """Find a move that creates multiple winning opportunities."""
        best_col = None
        best_score = -1

        for col in game.available_columns():
            row = game.get_next_open_row(col)
            if row is not None:
                # Temporarily place piece
                game.board[row][col] = self.piece

                # Count potential winning moves this creates
                score = self.count_threats(game, self.piece)

                # Remove piece
                game.board[row][col] = ' '

                if score > best_score:
                    best_score = score
                    best_col = col

        return best_col if best_score > 0 else None

    def count_threats(self, game, piece):
        """Count the number of ways the piece could win in the next move."""
        threats = 0
        for col in game.available_columns():
            row = game.get_next_open_row(col)
            if row is not None:
                game.board[row][col] = piece
                if game.check_winner(row, col, piece):
                    threats += 1
                game.board[row][col] = ' '
        return threats


def play(game, red_player, yellow_player, print_game=True):
    """Main game loop."""
    piece = 'R'  # Red goes first

    while not game.is_full():
        # Get the move from the appropriate player
        if piece == 'Y':
            col = yellow_player.get_move(game)
        else:
            col = red_player.get_move(game)

        # Make the move
        if game.make_move(col, piece):
            if print_game:
                print(f"\n{piece} drops a piece in column {col}")
                game.print_board()

            if game.current_winner:
                if print_game:
                    color = "Red" if piece == 'R' else "Yellow"
                    print(f"{color} ({piece}) wins!")
                return piece

            # Alternate pieces
            piece = 'Y' if piece == 'R' else 'R'
        else:
            if print_game:
                print("Invalid move. Try again.")

    if print_game:
        print("It's a tie! The board is full.")
    return None


def main():
    """Main entry point for the game."""
    print("=" * 50)
    print("Welcome to Connect 4!")
    print("=" * 50)
    print("\nConnect 4 pieces in a row to win!")
    print("You are Red (R), Computer is Yellow (Y)")
    print()

    # Set up players
    red_player = HumanPlayer('R')
    yellow_player = ComputerPlayer('Y')

    # Create and play the game
    game = Connect4()
    game.print_board()
    play(game, red_player, yellow_player)


if __name__ == '__main__':
    main()
