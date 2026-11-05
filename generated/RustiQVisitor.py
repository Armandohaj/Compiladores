# Generated from RustiQ.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .RustiQParser import RustiQParser
else:
    from RustiQParser import RustiQParser

# This class defines a complete generic visitor for a parse tree produced by RustiQParser.

class RustiQVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by RustiQParser#program.
    def visitProgram(self, ctx:RustiQParser.ProgramContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#functionDecl.
    def visitFunctionDecl(self, ctx:RustiQParser.FunctionDeclContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#block.
    def visitBlock(self, ctx:RustiQParser.BlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#statement.
    def visitStatement(self, ctx:RustiQParser.StatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#letDecl.
    def visitLetDecl(self, ctx:RustiQParser.LetDeclContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#assignment.
    def visitAssignment(self, ctx:RustiQParser.AssignmentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#returnStmt.
    def visitReturnStmt(self, ctx:RustiQParser.ReturnStmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#expression.
    def visitExpression(self, ctx:RustiQParser.ExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#additive.
    def visitAdditive(self, ctx:RustiQParser.AdditiveContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#multiplicative.
    def visitMultiplicative(self, ctx:RustiQParser.MultiplicativeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#unary.
    def visitUnary(self, ctx:RustiQParser.UnaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#primary.
    def visitPrimary(self, ctx:RustiQParser.PrimaryContext):
        return self.visitChildren(ctx)



del RustiQParser