grammar RustiQ;

// =====================================================
// 1. PROGRAMA, FUNCIONES Y TIPOS
// =====================================================

// El archivo puede contener funciones y constantes globales.
program
    : (functionDecl | constDecl)* EOF
    ;

// Constante global con tipo y valor obligatorios.
// Ejemplo: const LIMITE: i32 = 10;
constDecl
    : CONST IDENT COLON type ASSIGN expression SEMICOLON
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
// Tipos básicos y arreglos de tamaño fijo.
// Ejemplos: i32, String, [i32; 3], [[bool; 2]; 3].
type
    : I32
    | F64
    | BOOL
    | CHAR
    | STRING
    | LBRACKET type SEMICOLON INT RBRACKET
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
    : IDENT indexAccess* assignmentOp expression
    ;

// Cada acceso mantiene su propia expresión de índice.
// Permite destinos como matriz[0][1] sin cambiar el acceso
// al identificador y al valor de las asignaciones existentes.
indexAccess
    : LBRACKET expression RBRACKET
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

// Los operadores unarios se aplican después de los accesos.
// Ejemplo: -numeros[0].
unary
    : (MINUS | NOT)? postfix
    ;

// Acceso a elementos de arreglos.
// Permite accesos anidados: matriz[0][1].
postfix
    : primary (LBRACKET expression RBRACKET)*
    ;

// Valores básicos y expresiones entre paréntesis.
primary
    : INT
    | FLOAT
    | TRUE
    | FALSE
    | CHAR_LITERAL
    | STRING_LITERAL
    | arrayLiteral
    | functionCall
    | IDENT
    | LPAREN expression RPAREN
    ;

// Elementos separados por comas.
// Permite un arreglo vacío y una coma final.
arrayLiteral
    : LBRACKET (expression (COMMA expression)* COMMA?)? RBRACKET
    ;
// =====================================================
// 5. PALABRAS RESERVADAS
// =====================================================

FN       : 'fn';
RETURN   : 'return';
LET      : 'let';
MUT      : 'mut';
CONST    : 'const';
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
LBRACKET  : '[';
RBRACKET  : ']';
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