import tkinter as tk
from tkinter import messagebox

class TicTacToe:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Tic Tac Toe")
        self.window.geometry("300x300")
        self.player_turn = "X"
        self.board = [[None]*3 for _ in range(3)]
        self.buttons = []
        self.create_widgets()

    def create_widgets(self):
        for i in range(3):
            row = []
            for j in range(3):
                button = tk.Button(self.window, text="", command=lambda i=i, j=j: self.click(i, j), height=3, width=6)
                button.grid(row=i, column=j)
                row.append(button)
            self.buttons.append(row)

    def click(self, i, j):
        if self.board[i][j] is None:
            self.board[i][j] = self.player_turn
            if self.player_turn == "X":
                self.buttons[i][j].config(text="X")
                self.player_turn = "O"
            else:
                self.buttons[i][j].config(text="O")
                self.player_turn = "X"

            self.check_win()

    def check_win(self):
        for i in range(3):
            if self.board[i][0] == self.board[i][1] == self.board[i][2]:
                self.game_over(self.board[i][0])
            if self.board[0][i] == self.board[1][i] == self.board[2][i]:
                self.game_over(self.board[0][i])

        if self.board[0][0] == self.board[1][1] == self.board[2][2]:
            self.game_over(self.board[0][0])
        if self.board[0][2] == self.board[1][1] == self.board[2][0]:
            self.game_over(self.board[0][2])

    def game_over(self, winner):
        for i in range(3):
            for j in range(3):
                self.buttons[i][j].config(state='disabled')
        if winner is None:
            messagebox.showinfo("Game Over", "It's a draw!")
        else:
            if winner == 'X':
                messagebox.showinfo("Game Over", "Player X wins!")
            else:
                messagebox.showinfo("Game Over", "Player O wins!")

    def run(self):
        self.window.mainloop()

if __name__ == "__main__":
    game = TicTacToe()
    game.run()