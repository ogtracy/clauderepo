#!/usr/bin/env python3
"""
Tic-Tac-Toe Game
A simple tic-tac-toe game where a human player (X) plays against a computer (O).
"""

import random
import sys


class TicTacToe:
    def __init__(self):
        """Initialize the game board and game state."""
        self.board = [' ' for _ in range(9)]  # 3x3 board represented as a list
        self.current_winner = None

    def print_board(self):
        """Display the current game board."""
        print("\n")
        for row in [self.board[i*3:(i+1)*3] for i in range(3)]:
            print('| ' + ' | '.join(row) + ' |')
        print("\n")

    @staticmethod
    def print_board_nums():
        """Display the board with position numbers for reference."""
        print("\nPosition numbers:")
        number_board = [[str(i) for i in range(j*3, (j+1)*3)] for j in range(3)]
        for row in number_board:
            print('| ' + ' | '.join(row) + ' |')
        print()

    def available_moves(self):
        """Return a list of available positions on the board."""
        return [i for i, spot in enumerate(self.board) if spot == ' ']

    def empty_squares(self):
        """Check if there are any empty squares left."""
        return ' ' in self.board

    def num_empty_squares(self):
        """Count the number of empty squares."""
        return self.board.count(' ')

    def make_move(self, square, letter):
        """
        Place a letter (X or O) on the specified square.
        Returns True if the move was valid, False otherwise.
        """
        if self.board[square] == ' ':
            self.board[square] = letter
            if self.winner(square, letter):
                self.current_winner = letter
            return True
        return False

    def winner(self, square, letter):
        """Check if the last move resulted in a win."""
        # Check row
        row_ind = square // 3
        row = self.board[row_ind*3:(row_ind+1)*3]
        if all([spot == letter for spot in row]):
            return True

        # Check column
        col_ind = square % 3
        column = [self.board[col_ind+i*3] for i in range(3)]
        if all([spot == letter for spot in column]):
            return True

        # Check diagonals
        if square % 2 == 0:  # Only corners and center are on diagonals
            diagonal1 = [self.board[i] for i in [0, 4, 8]]
            if all([spot == letter for spot in diagonal1]):
                return True
            diagonal2 = [self.board[i] for i in [2, 4, 6]]
            if all([spot == letter for spot in diagonal2]):
                return True

        return False


class HumanPlayer:
    def __init__(self, letter):
        """Initialize a human player with their letter (X or O)."""
        self.letter = letter

    def get_move(self, game):
        """Get a valid move from the human player."""
        valid_square = False
        val = None
        while not valid_square:
            square = input(f"{self.letter}'s turn. Enter move (0-8): ")
            try:
                val = int(square)
                if val not in game.available_moves():
                    raise ValueError
                valid_square = True
            except ValueError:
                print("Invalid move. Try again.")
        return val


class ComputerPlayer:
    def __init__(self, letter):
        """Initialize a computer player with their letter (X or O)."""
        self.letter = letter

    def get_move(self, game):
        """Get a move for the computer player using a simple AI strategy."""
        if len(game.available_moves()) == 9:
            # First move - pick a random corner or center
            square = random.choice([0, 2, 4, 6, 8])
        else:
            # Try to win first
            square = self.find_winning_move(game, self.letter)
            if square is None:
                # Block opponent from winning
                opponent = 'O' if self.letter == 'X' else 'X'
                square = self.find_winning_move(game, opponent)
            if square is None:
                # Take center if available
                if 4 in game.available_moves():
                    square = 4
                else:
                    # Take a corner
                    corners = [i for i in [0, 2, 6, 8] if i in game.available_moves()]
                    if corners:
                        square = random.choice(corners)
                    else:
                        # Take any available spot
                        square = random.choice(game.available_moves())

        return square

    def find_winning_move(self, game, letter):
        """Find a move that would result in a win for the given letter."""
        for move in game.available_moves():
            # Simulate the move
            test_board = game.board.copy()
            test_board[move] = letter

            # Check if this move wins
            # Check row
            row_ind = move // 3
            row = test_board[row_ind*3:(row_ind+1)*3]
            if all([spot == letter for spot in row]):
                return move

            # Check column
            col_ind = move % 3
            column = [test_board[col_ind+i*3] for i in range(3)]
            if all([spot == letter for spot in column]):
                return move

            # Check diagonals
            if move % 2 == 0:
                diagonal1 = [test_board[i] for i in [0, 4, 8]]
                if all([spot == letter for spot in diagonal1]):
                    return move
                diagonal2 = [test_board[i] for i in [2, 4, 6]]
                if all([spot == letter for spot in diagonal2]):
                    return move

        return None


def play(game, x_player, o_player, print_game=True):
    """Main game loop."""
    if print_game:
        game.print_board_nums()

    letter = 'X'  # X goes first

    while game.empty_squares():
        # Get the move from the appropriate player
        if letter == 'O':
            square = o_player.get_move(game)
        else:
            square = x_player.get_move(game)

        # Make the move
        if game.make_move(square, letter):
            if print_game:
                print(f"\n{letter} makes a move to square {square}")
                game.print_board()

            if game.current_winner:
                if print_game:
                    print(f"{letter} wins!")
                return letter

            # Alternate letters
            letter = 'O' if letter == 'X' else 'X'

    if print_game:
        print("It's a tie!")
    return None


def main():
    """Main entry point for the game."""
    print("=" * 40)
    print("Welcome to Tic-Tac-Toe!")
    print("=" * 40)

    # Set up players
    x_player = HumanPlayer('X')
    o_player = ComputerPlayer('O')

    # Create and play the game
    game = TicTacToe()
    play(game, x_player, o_player)


if __name__ == '__main__':
    main()
