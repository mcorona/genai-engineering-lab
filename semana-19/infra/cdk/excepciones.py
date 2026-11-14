"""Week 19, activity 3: every wildcard the stacks keep, by statement Sid, with its reason. No AWS imports, so the
no-AWS tests can read it. The tests fail if a wildcard appears under a Sid that is not here, or if an entry is stale."""

# Every wildcard that remains, by statement Sid, with the reason. The test fails if a wildcard appears with a Sid
# that is not here, or if an entry here no longer exists. The same reasons go to cdk-nag suppressions.
EXCEPCIONES = {
    "CrearKnowledgeBasePorCfn": "bedrock:CreateKnowledgeBase no tiene ARN antes de crear la Knowledge Base: AWS la autoriza contra '*' (verificado con iam simulate-custom-policy).",
    "BaseDeDatosPostgresPorCfn": "Crear, modificar y borrar la base y su subnet group: el nombre lo pone CloudFormation con el prefijo semana19-datos; la base no tiene ARN antes de crearse.",
    "BucketDocsKbPorCfn": "Bucket de documentos de la Knowledge Base: CloudFormation le pone nombre con el prefijo semana19-datos; el borrado de objetos se necesita para el teardown.",
    "VectoresKbPorCfn": "Bucket e índice de S3 Vectors con el prefijo semana19-kb-; el índice se crea dentro del bucket y su ARN no existe antes del despliegue.",
    "KnowledgeBasePorCfn": "Knowledge Base y su fuente de datos: el ID lo asigna Bedrock al crearse, así que el ARN es knowledge-base/* dentro de la región y cuenta.",
    "RolesDelDatosPorCfn": "Roles del stack datos (semana19-kb y semana19-datos-*): sus políticas en línea y adjuntas las pone CloudFormation; los roles llevan el límite semana19-limite, que acota lo que pueden tener.",
    "PasarRolesDelDatosAKbYLambda": "iam:PassRole de los roles del stack datos solo hacia bedrock y lambda (condición PassedToService).",
    "ConcurrenciaDelCargador": "Concurrencia reservada de la Lambda del cargador: su nombre tiene el prefijo semana19-.",
    "SecretoDeLaBdPorCfn": "Secrets Manager crea el secreto con nombre generado por CloudFormation: el ARN no existe antes de crearlo; AWS exige '*' para Create*.",
    "ContrasenaGeneradaPorCfn": "GetRandomPassword no admite ARN de recurso: AWS exige '*'.",
    "DescribirRdsPorCfn": "rds:Describe* no acepta ARN de recurso para listar instancias y subnet groups: AWS exige '*'.",
    "LlaveParaRdsYSecretos": "kms:CreateGrant y ListGrants para que RDS y Secrets Manager usen la llave del proyecto; el recurso es la llave (AWS exige '*' en la política de ejecución) y la condición kms:ViaService limita el uso a esos dos servicios.",
    "LeerLosDocs": "Lectura de los documentos del diccionario bajo el prefijo docs/ del bucket de la Knowledge Base, para el rol de Bedrock; el ARN de objeto se acota al prefijo.",
    "EscribirDocsKb": "Escritura de los documentos del diccionario bajo el prefijo docs/ del bucket de la Knowledge Base; CloudFormation y AWS exigen el ARN de objeto con clave, así que el comodín queda acotado al prefijo.",
    "LeerInventario": "Acciones de descripción y listado de AWS que no admiten ARN de recurso (describe/list): resource '*' con solo lectura; el rol del operador no puede crear, cambiar ni borrar.",
    "LogsDelGrupoDelProyecto": "Nombre por prefijo: los grupos del proyecto empiezan por /semana19/. El recurso no tiene ARN previo.",
    "LogsDescribir": "logs:DescribeLogGroups no acepta ARN de recurso: AWS exige resource '*'.",
    "CdkAssumeRoles": "Nombre por prefijo: los roles del bootstrap llevan la cuenta y la región en el nombre (cdk-s19-*-<cuenta>-us-east-1); la cuenta no se escribe en el repo.",
    "CloudFormationLeer": "Describe, Get y List de CloudFormation: AWS no los acepta con ARN de recurso para listar stacks.",
    "RestringirSgPorDefecto": "ec2:DescribeSecurityGroups no acepta ARN; Revoke* sobre el grupo por defecto lo usa el custom resource de CDK que vacía sus reglas.",
    "NoCrearNiActualizarMientrasEsteActiva": "Denegación de acciones Create*/Update*: el recurso que se va a crear aún no tiene ARN; AWS exige '*'. Solo deniega crear y actualizar; borrar sigue permitido.",
    "VpcYRedes": "Acciones de creación de VPC, subredes, grupos y endpoints: el recurso aún no existe (AWS exige '*'); ec2:Describe* no acepta ARN.",
    "LlavesKms": "kms:CreateKey exige resource '*' (la llave aún no existe); las demás acciones usan '*' porque la llave la crea el mismo stack.",
    "GruposDeLogs": "Nombre por prefijo: /semana19/*. El stack crea el grupo con ese nombre.",
    "DescribirGruposDeLogs": "logs:DescribeLogGroups no acepta ARN de recurso.",
    "FuncionesDeCustomResourceDelProyecto": "Nombre por prefijo: las funciones de custom resource del stack empiezan por semana19-.",
    "PasarRolDelCustomResourceDelProyecto": "Nombre con sufijo generado por CDK (semana19-base-CustomVpcRestrictDefaultSGCustomResou*): el sufijo no existe antes del despliegue. Solo PassRole, solo a lambda.amazonaws.com.",
    "PoliticasYAdjuntosDeRolesDelBase": "Nombres generados por CDK bajo semana19-base-* (sufijo aleatorio). Sin la condición de límite: PutRolePolicy/AttachRolePolicy no reciben la clave PermissionsBoundary en la llamada. El límite sigue acotando lo que el rol puede hacer; no se quita ni se cambia (NoQuitarNiCambiarElLimite).",
    "BorrarRolesDelBase": "Nombres generados por CDK bajo semana19-base-* (sufijo aleatorio): DeleteRole no recibe la clave PermissionsBoundary. Solo roles de este stack.",
    "LeerActivosDelBootstrap": "Bucket de activos del bootstrap (nombre con la cuenta, no escrito en el repo). Solo lectura de objetos: CloudFormation lee el zip de la Lambda del custom resource.",
    "DescifrarActivosConS3": "kms:Decrypt sobre la llave administrada aws/s3 (no hay ARN de llave fijo en el repo): solo cuando la llamada viene de S3 en us-east-1 (kms:ViaService).",
    "RolesConLimite": "Nombre por prefijo semana19-*, y la condición iam:PermissionsBoundary obliga el límite en la creación.",
    "AsumirRolesCdk": "Nombre por prefijo: cdk-s19-*-<cuenta>-us-east-1 (la cuenta no se escribe en el repo).",
    "LeerCloudFormation": "Describe, Get y List de CloudFormation: sin ARN de recurso para listar.",
    "CrearRolesSoloConLimite": "Nombre por prefijo semana19-*, y la condición obliga el límite.",
    "NoQuitarNiCambiarElLimite": "Denegación sobre roles semana19-* por prefijo.",
    "RaizDeLaCuenta": "Política de llave: kms:* para la raíz (delegación a IAM). En una política de llave, resource '*' significa esta llave; AWS lo exige.",
    "LogsDelProyectoConLaLlave": "Política de llave: resource '*' significa esta llave; AWS lo exige. La condición EncryptionContext limita al grupo /semana19/*.",
    "RolesConNombre": "Política de llave: resource '*' significa esta llave; AWS lo exige.",
    "EscribirSoloEnSuGrupo": "Los flow logs escriben en los streams del grupo: AWS exige la forma <grupo>:* .",
    "DescribirGruposParaFlowLogs": "logs:DescribeLogGroups no acepta ARN de recurso.",
    "-": "Statement sin Sid generado por CDK para el destino de los flow logs (log-group:*). Mismo motivo que EscribirSoloEnSuGrupo.",
}

# Roles that may create IAM roles besides the deploy role. Decided by Manuel on 2026-11-14 (documented exception).
# The test fails if a statement with iam:CreateRole belongs to a role not listed here, if it lacks the boundary
# condition, or if an entry here no longer creates roles.
ROLES_QUE_PUEDEN_CREAR_ROLES = {
    "EjecucionCfn": "Excepción documentada: el rol de ejecución de CloudFormation crea roles solo con nombre semana19* y "
                    "solo con el permission boundary semana19-limite. CloudFormation necesita ese permiso para crear los "
                    "roles de los stacks; sin él no puede desplegar el stack base.",
}
