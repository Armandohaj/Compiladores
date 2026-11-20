grammar RustiQ;

// =====================================================
// 1. PROGRAMA, FUNCIONES Y TIPOS
// =====================================================

// Declaraciones permitidas en el archivo.
program
    : (functionDecl | constDecl | structDecl | enumDecl)* EOF
    ;
// Una enumeración debe declarar al menos una variante.
// Ejemplo: enum Estado { Pendiente, Completado }
enumDecl
    : ENUM IDENT LBRACE variantDecl (COMMA variantDecl)* COMMA? RBRACE
    ;

// Variante sin datos o con tipos asociados.
// Ejemplos: Vacio, Correcto(i32), Coordenada(i32, i32).
variantDecl
    : IDENT (LPAREN variantTypeList RPAREN)?
    ;

// Lista de tipos que necesita la variante.
// Separa los tipos con comas y permite una coma final.
variantTypeList
    : type (COMMA type)* COMMA?
    ;

// Construcción de un valor de enumeración.
//
// Ejemplos:
// Resultado::Vacio
// Resultado::Correcto(10)
// Resultado::Error("Archivo no encontrado")
//
// La gramática reconoce la forma de la llamada.
// El semántico comprobará si la variante necesita datos,
// cuántos recibe y si sus tipos son compatibles.
enumValue
    : IDENT DOUBLE_COLON IDENT (LPAREN argumentList? RPAREN)?
    ;

// Estructura nominal: cada nombre define un tipo diferente.
// Todos sus campos deben indicarse al construir un valor.
structDecl
    : STRUCT IDENT LBRACE (fieldDecl (COMMA fieldDecl)* COMMA?)? RBRACE
    ;

fieldDecl
    : IDENT COLON type
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
    : AMP MUT? type
    | I32
    | F64
    | BOOL
    | CHAR
    | STRING
    | LBRACKET type SEMICOLON INT RBRACKET
    | LPAREN type COMMA type (COMMA type)* COMMA? RPAREN
    | IDENT
    ;
// =====================================================
// 2. BLOQUES Y SENTENCIAS
// =====================================================

// Un bloque contiene sentencias y una expresión final opcional.
// Las sentencias realizan acciones.
// La expresión final, sin punto y coma, produce el valor del bloque.
//
// Ejemplo:
// {
//     let base = 10;
//     base + 1
// }
//
// Si no tiene expresión final, su tipo será unit.
// El analizador semántico comprobará esos tipos.
block
    : LBRACE statement* expression? RBRACE
    ;
statement
    : constLocalDecl
    | letDecl
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
    : IDENT (indexAccess | tupleAccess | fieldAccess)* assignmentOp expression
    | dereferenceTarget assignmentOp expression
    ;

// Escritura a través de una referencia simple: *referencia = valor.
dereferenceTarget
    : STAR IDENT
    ;

// Cada acceso mantiene su propia expresión de índice.
// Permite destinos como matriz[0][1] sin cambiar el acceso
// al identificador y al valor de las asignaciones existentes.
indexAccess
    : LBRACKET expression RBRACKET
    ;

// Acceso por posición a una tupla, por ejemplo dato.0.
// TUPLE_FIELD evita que dato.0.1 se confunda con un decimal.
// La alternativa DOT INT admite espacios entre el punto y el número.
tupleAccess
    : TUPLE_FIELD
    | DOT INT
    ;

// Acceso a un campo por nombre: persona.edad.
fieldAccess
    : DOT IDENT
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
    : (MINUS | NOT)? (borrowExpr | dereferenceExpr | postfix)
    ;

// El semántico limita inicialmente el destino a una variable completa.
borrowExpr
    : AMP MUT? unary
    ;

// El operando debe tener tipo &T o &mut T.
dereferenceExpr
    : STAR unary
    ;

// Acceso a elementos de arreglos.
// Permite accesos anidados: matriz[0][1].
postfix
    : primary (LBRACKET expression RBRACKET | tupleAccess | fieldAccess)*
    ;

// Valores básicos que pueden formar una expresión.
// match también produce un valor, como un número o una llamada.
primary
    : INT
    | FLOAT
    | TRUE
    | FALSE
    | CHAR_LITERAL
    | STRING_LITERAL
    | arrayLiteral
    | tupleLiteral
    | functionCall
    | enumValue
    | IDENT
    | structLiteral
    | matchExpr
    | block
    | LPAREN expression RPAREN
    ;
// =====================================================
// MATCH Y PATRONES
// =====================================================

// Evalúa un valor y selecciona el primer brazo compatible.
// Debe tener al menos un brazo y permite una coma final.
// Ejemplo: match numero { 0 => 10, _ => 20 }
matchExpr
    : MATCH expression LBRACE matchArm (COMMA matchArm)* COMMA? RBRACE
    ;

// Cada brazo relaciona un patrón con una expresión.
// La comprobación de tipos corresponde al analizador semántico.
matchArm
    : pattern FAT_ARROW expression
    ;

// Formas de reconocer el valor evaluado:
// _                        ignora cualquier valor.
// 10, true, 'a'            comparan un literal.
// Resultado::Correcto(x)   reconoce una variante y extrae sus datos.
// (x, _)                  descompone una tupla.
// nombre                  recibe el valor en una variable local.
pattern
    : UNDERSCORE
    | patternLiteral
    | IDENT DOUBLE_COLON IDENT (LPAREN patternList RPAREN)?
    | LPAREN pattern COMMA pattern (COMMA pattern)* COMMA? RPAREN
    | IDENT
    ;

// Patrones de los datos asociados a una variante.
// También permite patrones anidados.
patternList
    : pattern (COMMA pattern)* COMMA?
    ;

// Los números negativos incluyen el signo en el patrón.
// Aquí no se admiten operaciones como 1 + 2.
patternLiteral
    : MINUS? INT
    | MINUS? FLOAT
    | TRUE
    | FALSE
    | CHAR_LITERAL
    | STRING_LITERAL
    ;

// Construcción de una estructura. El orden de los campos puede variar.
// Ejemplo: Persona { edad: 20, activo: true }.
structLiteral
    : IDENT LBRACE (fieldInit (COMMA fieldInit)* COMMA?)? RBRACE
    ;

fieldInit
    : IDENT COLON expression
    ;

// Tupla de dos o más elementos, que pueden tener distintos tipos.
// Una sola expresión entre paréntesis sigue siendo agrupación.
tupleLiteral
    : LPAREN expression COMMA expression (COMMA expression)* COMMA? RPAREN
    ;

// Elementos separados por comas.
// Permite un arreglo vacío y una coma final.
arrayLiteral
    : LBRACKET (expression (COMMA expression)* COMMA?)? RBRACKET
    ;
// =====================================================
// 5. PALABRAS RESERVADAS
// =====================================================
// Palabra reservada y símbolos utilizados por match.
// UNDERSCORE debe aparecer antes de IDENT para distinguir
// el comodín "_" de un nombre de variable.
MATCH      : 'match';
FAT_ARROW  : '=>';
UNDERSCORE : '_';
STRUCT   : 'struct';
ENUM     : 'enum';
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
DOUBLE_COLON : '::';
COLON     : ':';
COMMA     : ',';
// Un campo completo permite encadenar .0.1 sin consumir FLOAT.
TUPLE_FIELD : '.' [0-9]+;
DOT         : '.';

EQ     : '==';
NEQ    : '!=';
LE     : '<=';
GE     : '>=';
LT     : '<';
GT     : '>';

AMP    : '&';
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
// Constante con ámbito léxico: tipo e inicializador obligatorios.
constLocalDecl
    : CONST IDENT COLON type ASSIGN expression SEMICOLON
    ;
