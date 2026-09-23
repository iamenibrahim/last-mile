targetScope = 'resourceGroup'

@description('Short lowercase project prefix. Globally unique suffixes are added automatically.')
@minLength(3)
@maxLength(12)
param namePrefix string = 'lastmile'

@description('Use a region that supports the intended Microsoft Foundry model.')
param location string

@description('Foundry model deployment name configured in the application. Deploy the model separately after checking regional availability.')
param foundryModelDeployment string = 'last-mile-gpt'

@description('Foundry embedding deployment name for the semantic-fidelity check. Deploy it separately, like the chat model.')
param foundryEmbeddingDeployment string = 'text-embedding-3-small'

var suffix = uniqueString(subscription().subscriptionId, resourceGroup().id)
var safeName = toLower('${namePrefix}${suffix}')
var tags = {
  project: 'last-mile-navigator'
  environment: 'student-hackathon'
  costProfile: 'free-and-consumption'
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take('${safeName}fn', 24)
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource functionsPlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${namePrefix}-consumption'
  location: location
  tags: tags
  kind: 'linux'
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
  properties: { reserved: true }
}

resource foundry 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${safeName}foundry'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: '${safeName}foundry'
    publicNetworkAccess: 'Enabled'
    networkAcls: { defaultAction: 'Allow' }
    disableLocalAuth: false
  }
}

resource translator 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${safeName}translator'
  location: 'global'
  tags: tags
  kind: 'TextTranslation'
  sku: { name: 'F0' }
  properties: {
    customSubDomainName: '${safeName}translator'
    publicNetworkAccess: 'Enabled'
  }
}

resource speech 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${safeName}speech'
  location: location
  tags: tags
  kind: 'SpeechServices'
  sku: { name: 'F0' }
  properties: {
    customSubDomainName: '${safeName}speech'
    publicNetworkAccess: 'Enabled'
  }
}

resource contentSafety 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${safeName}safety'
  location: location
  tags: tags
  kind: 'ContentSafety'
  sku: { name: 'F0' }
  properties: {
    customSubDomainName: '${safeName}safety'
    publicNetworkAccess: 'Enabled'
  }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: '${safeName}cosmos'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: true
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    publicNetworkAccess: 'Enabled'
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: cosmos
  name: 'last-mile'
  properties: {
    resource: { id: 'last-mile' }
    options: { throughput: 400 }
  }
}

resource renders 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  parent: database
  name: 'renders'
  properties: {
    resource: {
      id: 'renders'
      partitionKey: {
        paths: ['/cap_id']
        kind: 'Hash'
      }
    }
  }
}

resource maps 'Microsoft.Maps/accounts@2023-06-01' = {
  name: '${safeName}maps'
  location: 'global'
  tags: tags
  kind: 'Gen2'
  sku: { name: 'G2' }
  properties: { disableLocalAuth: false }
}

resource communication 'Microsoft.Communication/communicationServices@2023-04-01' = {
  name: '${safeName}communication'
  location: 'global'
  tags: tags
  properties: { dataLocation: 'United States' }
}

// Request latency and failures for the pitch's live numbers. The workspace has a
// hard daily ingestion cap well inside the 5 GB/month free allowance, so it
// cannot run up the student credit. The Functions host sends request telemetry
// on its own; the app adds no custom logging of what people type.
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${safeName}logs'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    workspaceCapping: { dailyQuotaGb: json('0.1') }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${safeName}insights'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
    DisableIpMasking: false
  }
}

// Manifest and packet signing. RS256 key; the private half never leaves the vault,
// and GET /api/signing-key publishes the public half. Standard tier, pay per
// operation (fractions of a cent at demo volume).
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: take('kv${safeName}', 24)
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    softDeleteRetentionInDays: 7
  }
}

resource signingKey 'Microsoft.KeyVault/vaults/keys@2023-07-01' = {
  parent: keyVault
  name: 'manifest-signing'
  properties: {
    kty: 'RSA'
    keySize: 2048
    keyOps: [ 'sign', 'verify' ]
  }
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: '${safeName}api'
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: functionsPlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|3.12'
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      functionAppScaleLimit: 2
      appSettings: [
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'AzureWebJobsStorage', value: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}' }
        { name: 'APP_ENV', value: 'azure' }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        { name: 'PUBLIC_BASE_URL', value: 'https://${safeName}api.azurewebsites.net' }
        { name: 'AZURE_USE_MANAGED_IDENTITY', value: 'true' }
        { name: 'AZURE_FOUNDRY_ENDPOINT', value: 'https://${foundry.name}.openai.azure.com' }
        { name: 'AZURE_FOUNDRY_MODEL', value: foundryModelDeployment }
        { name: 'AZURE_FOUNDRY_EMBED_MODEL', value: foundryEmbeddingDeployment }
        { name: 'AZURE_FOUNDRY_API_KEY', value: foundry.listKeys().key1 }
        { name: 'AZURE_KEYVAULT_URL', value: keyVault.properties.vaultUri }
        { name: 'AZURE_KEYVAULT_KEY_NAME', value: signingKey.name }
        { name: 'AZURE_TRANSLATOR_KEY', value: translator.listKeys().key1 }
        { name: 'AZURE_TRANSLATOR_REGION', value: 'global' }
        { name: 'AZURE_SPEECH_KEY', value: speech.listKeys().key1 }
        { name: 'AZURE_SPEECH_REGION', value: location }
        { name: 'AZURE_CONTENT_SAFETY_ENDPOINT', value: contentSafety.properties.endpoint }
        { name: 'AZURE_CONTENT_SAFETY_KEY', value: contentSafety.listKeys().key1 }
        { name: 'AZURE_MAPS_KEY', value: maps.listKeys().primaryKey }
        { name: 'AZURE_COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
        { name: 'AZURE_COMMUNICATION_ENDPOINT', value: 'https://${communication.name}.communication.azure.com' }
        { name: 'SMS_SEND_ENABLED', value: 'false' }
        { name: 'SMS_AUTOREPLY_ENABLED', value: 'false' }
      ]
    }
  }
}

resource foundryUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, functionApp.id, 'openai-user')
  scope: foundry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource keyVaultCryptoUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, functionApp.id, 'crypto-user')
  scope: keyVault
  properties: {
    // Key Vault Crypto User: sign and verify with keys, no key management.
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '12338af0-0e69-4776-bea7-57ae8d297424')
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource cosmosDataRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: cosmos
  name: guid(cosmos.id, functionApp.id, 'data-contributor')
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    principalId: functionApp.identity.principalId
    scope: cosmos.id
  }
}

output functionAppName string = functionApp.name
output applicationUrl string = 'https://${functionApp.properties.defaultHostName}'
output foundryResourceName string = foundry.name
output foundryEndpoint string = 'https://${foundry.name}.openai.azure.com'
output cosmosFreeTier bool = cosmos.properties.enableFreeTier
output keyVaultUri string = keyVault.properties.vaultUri
output communicationEndpoint string = 'https://${communication.name}.communication.azure.com'
output costGuardrails array = [
  'Azure Functions Dynamic Y1 plan; scales to zero and is capped at two instances.'
  'Cosmos DB lifetime free tier with 400 RU/s shared throughput.'
  'Translator, Speech, and Content Safety use F0 tiers.'
  'Foundry is pay-per-token; no model is deployed by this template.'
  'Key Vault Standard; one RSA key, billed per signing operation.'
  'Application Insights on a Log Analytics workspace capped at 0.1 GB/day, 30-day retention.'
  'SMS sending and automatic replies remain disabled.'
  'No always-on App Service, Premium plan, VM, or managed GPU is deployed.'
]
