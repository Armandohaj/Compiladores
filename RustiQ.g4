grammar RustiQ;

// =====================================================
// 1. PROGRAMA, FUNCIONES Y TIPOS
// =====================================================

program
    : functionDecl* EOF
    ;

// Parámetros y retorno opcionales.
functionDecl
    : FN IDENT LPAREN parameterList? RPAREN (ARROW type)? block
    ;

parameterList
    : parameter (COMMA parameter)* COMMA?
    ;

parameter
    : MUT? IDENT COLON type
    ;

// String distingue mayúsculas y minúsculas.
type
    : I32
    | F64
    | BOOL
    | CHAR
    | STRING
    ;

// =====================================================
// 2. BLOQUES Y SENTENCIAS
// =====================================================

block
    : LBRACE statement* RBRACE
    ;

statement
    : letDecl
    | assignment SEMICOLON
    | functionCall SEMICOLON
    | returnStmt
    | ifStmt
    | whileStmt
    | loopStmt
    | breakStmt
    | continueStmt
    | block
    ;

letDecl
    : LET MUT? IDENT (COLON type)? (ASSIGN expression)? SEMICOLON
    ;

// Asignación simple o compuesta a una variable.
assignment
    : IDENT assignmentOp expression
    ;

// El análisis semántico comprobará mutabilidad,
// inicialización y compatibilidad de tipos.
assignmentOp
    : ASSIGN
    | PLUS_ASSIGN
    | MINUS_ASSIGN
    | STAR_ASSIGN
    | SLASH_ASSIGN
    ;
returnStmt
    : RETURN expression? SEMICOLON
    ;

ifStmt
    : IF expression block (ELSE (block | ifStmt))?
    ;

whileStmt
    : WHILE expression block
    ;

// Ciclo sin condición.
// break permite salir y continue inicia otra iteración.
loopStmt
    : LOOP block
    ;

breakStmt
    : BREAK SEMICOLON
    ;

continueStmt
    : CONTINUE SEMICOLON
    ;

// =====================================================
// 3. LLAMADAS A FUNCIONES
// =====================================================

functionCall
    : IDENT LPAREN argumentList? RPAREN
    ;

argumentList
    : expression (COMMA expression)* COMMA?
    ;

// =====================================================
// 4. EXPRESIONES Y PRIORIDAD
// =====================================================

expression
    : logicalOr
    ;

logicalOr
    : logicalAnd (OR logicalAnd)*
    ;

logicalAnd
    : comparison (AND comparison)*
    ;

comparison
    : additive (relOp additive)?
    ;

relOp
    : EQ
    | NEQ
    | LT
    | LE
    | GT
    | GE
    ;

additive
    : multiplicative ((PLUS | MINUS) multiplicative)*
    ;

multiplicative
    : unary ((STAR | SLASH | PERCENT) unary)*
    ;

unary
    : (MINUS | NOT)? primary
    ;

// Los caracteres usan comillas simples.
// Las cadenas usan comillas dobles.
primary
    : INT
    | FLOAT
    | TRUE
    | FALSE
    | CHAR_LITERAL
    | STRING_LITERAL
    | functionCall
    | IDENT
    | LPAREN expression RPAREN
    ;

// =====================================================
// 5. PALABRAS RESERVADAS
// =====================================================

FN       : 'fn';
RETURN   : 'return';
LET      : 'let';
MUT      : 'mut';
IF       : 'if';
ELSE     : 'else';
WHILE    : 'while';
LOOP     : 'loop';
BREAK    : 'break';
CONTINUE : 'continue';

I32      : 'i32';
F64      : 'f64';
BOOL     : 'bool';
CHAR     : 'char';
STRING   : 'String';

TRUE     : 'true';
FALSE    : 'false';

// =====================================================
// 6. SÍMBOLOS Y OPERADORES
// =====================================================

LPAREN    : '(';
RPAREN    : ')';
LBRACE    : '{';
RBRACE    : '}';
ARROW     : '->';
SEMICOLON : ';';
COLON     : ':';
COMMA     : ',';

EQ     : '==';
NEQ    : '!=';
LE     : '<=';
GE     : '>=';
LT     : '<';
GT     : '>';

AND    : '&&';
OR     : '||';
NOT    : '!';

// Operadores de asignación compuesta.
PLUS_ASSIGN  : '+=';
MINUS_ASSIGN : '-=';
STAR_ASSIGN  : '*=';
SLASH_ASSIGN : '/=';

ASSIGN  : '=';
PLUS    : '+';
MINUS   : '-';
STAR    : '*';
SLASH   : '/';
PERCENT : '%';

// =====================================================
// 7. IDENTIFICADORES Y NÚMEROS
// =====================================================

IDENT
    : [a-zA-Z_] [a-zA-Z_0-9]*
    ;

FLOAT
    : [0-9]+ '.' [0-9]+
    ;

INT
    : [0-9]+
    ;

// =====================================================
// 8. CARACTERES Y CADENAS
// =====================================================

// Exactamente un carácter normal o una secuencia de escape.
// Ejemplos: 'A', 'ñ', '\n' y '\''.
// No permite un carácter vacío ni varios caracteres.
CHAR_LITERAL
    : '\'' (ESCAPE_SEQUENCE | ~['\\\r\n]) '\''
    ;

// Cero o más caracteres entre comillas dobles.
// No permite saltos de línea escritos directamente.
// Para representarlos se utiliza \n.
STRING_LITERAL
    : '"' (ESCAPE_SEQUENCE | ~["\\\r\n])* '"'
    ;

// Fragmento auxiliar: no produce un token independiente.
// Escapes admitidos:
// \n  salto de línea
// \r  retorno de carro
// \t  tabulación
// \0  carácter nulo
// \"  comilla doble
// \'  comilla simple
// \\  barra invertida
fragment ESCAPE_SEQUENCE
    : '\\' [nrt0"'\\]
    ;

// =====================================================
// 9. COMENTARIOS Y ESPACIOS
// =====================================================

LINE_COMMENT
    : '//' ~[\r\n]* -> skip
    ;

BLOCK_COMMENT
    : '/*' .*? '*/' -> skip
    ;

WS
    : [ \t\r\n]+ -> skip
    ;