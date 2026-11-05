grammar RustiQ;

// Un programa contiene cero o más funciones.
program
    : functionDecl* EOF
    ;

// Ejemplo: fn main() -> i32 { return 10 + 20; }
functionDecl
    : FN IDENT LPAREN RPAREN (ARROW I32)? block
    ;

block
    : LBRACE statement* RBRACE
    ;

statement
    : RETURN expression SEMICOLON
    ;

expression
    : INT (PLUS INT)*
    ;

// Palabras reservadas
FN     : 'fn';
RETURN : 'return';
I32    : 'i32';

// Símbolos
LPAREN    : '(';
RPAREN    : ')';
LBRACE    : '{';
RBRACE    : '}';
ARROW     : '->';
SEMICOLON : ';';
PLUS      : '+';

// Identificadores y números enteros
IDENT : [a-zA-Z_] [a-zA-Z_0-9]*;
INT   : [0-9]+;

// Ignorar comentarios y espacios
LINE_COMMENT  : '//' ~[\r\n]* -> skip;
BLOCK_COMMENT : '/*' .*? '*/' -> skip;
WS            : [ \t\r\n]+ -> skip;