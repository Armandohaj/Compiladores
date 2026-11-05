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


    # Visit a parse tree produced by RustiQParser#expression.
    def visitExpression(self, ctx:RustiQParser.ExpressionContext):
        return self.visitChildren(ctx)



del RustiQParser