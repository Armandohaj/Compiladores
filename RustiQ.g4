grammar RustiQ;

// =====================================================
// 1. PROGRAMA, FUNCIONES Y TIPOS
// =====================================================

// Un programa contiene cero o más funciones.
// EOF exige consumir todo el archivo.
program
    : functionDecl* EOF
    ;

// Los parámetros y el tipo de retorno son opcionales.
// Ejemplo: fn sumar(a: i32, b: i32) -> i32 { ... }
functionDecl
    : FN IDENT LPAREN parameterList? RPAREN (ARROW type)? block
    ;

// Parámetros separados por comas.
// También permite una coma después del último parámetro.
parameterList
    : parameter (COMMA parameter)* COMMA?
    ;

// Cada parámetro debe indicar su tipo.
// mut permite modificarlo dentro de la función.
parameter
    : MUT? IDENT COLON type
    ;

// Tipos disponibles.
type
    : I32
    | F64
    | BOOL
    ;

// =====================================================
// 2. BLOQUES Y SENTENCIAS
// =====================================================

// Grupo de sentencias entre llaves.
block
    : LBRACE statement* RBRACE
    ;

// Instrucciones disponibles dentro de un bloque.
// Una llamada también puede utilizarse como sentencia:
// procesar(10);
statement
    : letDecl
    | assignment SEMICOLON
    | functionCall SEMICOLON
    | returnStmt
    | ifStmt
    | whileStmt
    | breakStmt
    | continueStmt
    | block
    ;

// Variable con mutabilidad, tipo e inicializador opcionales.
letDecl
    : LET MUT? IDENT (COLON type)? (ASSIGN expression)? SEMICOLON
    ;

// Asignación a una variable.
assignment
    : IDENT ASSIGN expression
    ;

// Retorno con o sin valor.
returnStmt
    : RETURN expression? SEMICOLON
    ;

// Condicional con else o else if opcional.
ifStmt
    : IF expression block (ELSE (block | ifStmt))?
    ;

// La condición debe ser bool.
// El análisis semántico comprueba su tipo.
whileStmt
    : WHILE expression block
    ;

// Sale del ciclo más cercano.
breakStmt
    : BREAK SEMICOLON
    ;

// Pasa a la siguiente iteración del ciclo más cercano.
continueStmt
    : CONTINUE SEMICOLON
    ;

// =====================================================
// 3. LLAMADAS A FUNCIONES
// =====================================================

// Llamada con cero o más argumentos.
// Ejemplos: obtener() y sumar(10, 20).
functionCall
    : IDENT LPAREN argumentList? RPAREN
    ;

// Los argumentos son expresiones.
// Permite llamadas anidadas: sumar(obtener(), 20).
argumentList
    : expression (COMMA expression)* COMMA?
    ;

// =====================================================
// 4. EXPRESIONES Y PRIORIDAD
// =====================================================

expression
    : logicalOr
    ;

// O lógico.
logicalOr
    : logicalAnd (OR logicalAnd)*
    ;

// Y lógico: mayor prioridad que ||.
logicalAnd
    : comparison (AND comparison)*
    ;

// Comparación opcional entre expresiones aritméticas.
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

// Suma y resta.
additive
    : multiplicative ((PLUS | MINUS) multiplicative)*
    ;

// Multiplicación, división y residuo.
multiplicative
    : unary ((STAR | SLASH | PERCENT) unary)*
    ;

// Signo negativo o negación lógica opcional.
unary
    : (MINUS | NOT)? primary
    ;

// Valores básicos, llamadas y expresiones entre paréntesis.
// El resultado de una llamada puede participar en operaciones.
primary
    : INT
    | FLOAT
    | TRUE
    | FALSE
    | functionCall
    | IDENT
    | LPAREN expression RPAREN
    ;

// =====================================================
// 5. PALABRAS RESERVADAS
// =====================================================

// Se colocan antes de IDENT para distinguirlas
// de los nombres de variables y funciones.
FN       : 'fn';
RETURN   : 'return';
LET      : 'let';
MUT      : 'mut';
IF       : 'if';
ELSE     : 'else';
WHILE    : 'while';
BREAK    : 'break';
CONTINUE : 'continue';

I32      : 'i32';
F64      : 'f64';
BOOL     : 'bool';

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

// Separa parámetros y argumentos.
COMMA     : ',';

// Comparaciones.
EQ     : '==';
NEQ    : '!=';
LE     : '<=';
GE     : '>=';
LT     : '<';
GT     : '>';

// Operadores lógicos.
AND    : '&&';
OR     : '||';
NOT    : '!';

// Asignación y aritmética.
ASSIGN  : '=';
PLUS    : '+';
MINUS   : '-';
STAR    : '*';
SLASH   : '/';
PERCENT : '%';

// =====================================================
// 7. IDENTIFICADORES Y LITERALES
// =====================================================

// Nombres que comienzan con una letra o guion bajo.
IDENT
    : [a-zA-Z_] [a-zA-Z_0-9]*
    ;

// Decimales con dígitos antes y después del punto.
FLOAT
    : [0-9]+ '.' [0-9]+
    ;

// Enteros sin signo.
// El signo negativo se reconoce en unary.
INT
    : [0-9]+
    ;

// =====================================================
// 8. COMENTARIOS Y ESPACIOS
// =====================================================

// Ignorar comentarios de línea.
LINE_COMMENT
    : '//' ~[\r\n]* -> skip
    ;

// Ignorar comentarios de bloque sin anidamiento.
BLOCK_COMMENT
    : '/*' .*? '*/' -> skip
    ;

// Ignorar espacios, tabulaciones y saltos de línea.
WS
    : [ \t\r\n]+ -> skip
    ;