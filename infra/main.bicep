targetScope = 'resourceGroup'

@description('Short globally unique prefix, lowercase letters and numbers only.')
param namePrefix string

@description('Primary Azure region. Confirm Foundry model availability before deployment.')
param location string = resourceGroup().location

@description('Python API container image. Build and push before production deployment.')
param apiContainerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

var suffix = uniqueString(resourceGroup().id)
var safeName = toLower('${namePrefix}${suffix}')

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs'
  location: location
  properties: { retentionInDays: 30 }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${namePrefix}-insights'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${namePrefix}-plan'
  location: location
  kind: 'linux'
  sku: { name: 'B1', tier: 'Basic' }
  properties: { reserved: true }
}

resource foundry 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${safeName}foundry'
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: '${safeName}foundry'
    publicNetworkAccess: 'Enabled'
    networkAcls: { defaultAction: 'Allow' }
  }
}

resource speech 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${safeName}speech'
  location: location
  kind: 'SpeechServices'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: '${safeName}speech'
    publicNetworkAccess: 'Enabled'
  }
}

resource translator 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${safeName}translator'
  location: location
  kind: 'TextTranslation'
  sku: { name: 'S1' }
  properties: {
    customSubDomainName: '${safeName}translator'
    publicNetworkAccess: 'Enabled'
  }
}

resource contentSafety 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${safeName}safety'
  location: location
  kind: 'ContentSafety'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: '${safeName}safety'
    publicNetworkAccess: 'Enabled'
  }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: '${safeName}cosmos'
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [{ locationName: location, failoverPriority: 0, isZoneRedundant: false }]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    capabilities: [{ name: 'EnableServerless' }]
    publicNetworkAccess: 'Enabled'
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: cosmos
  name: 'last-mile'
  properties: { resource: { id: 'last-mile' } }
}

resource renders 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  parent: database
  name: 'renders'
  properties: {
    resource: {
      id: 'renders'
      partitionKey: { paths: ['/cap_id'], kind: 'Hash' }
    }
  }
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${safeName}kv'
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 30
    publicNetworkAccess: 'Enabled'
  }
}

resource maps 'Microsoft.Maps/accounts@2023-06-01' = {
  name: '${safeName}maps'
  location: 'global'
  kind: 'Gen2'
  sku: { name: 'G2' }
  properties: { disableLocalAuth: false }
}

// The resource itself is deployable on a student subscription. Azure does not
// provision a billable SMS number here; that remains an explicit portal step.
resource communication 'Microsoft.Communication/communicationServices@2023-04-01' = {
  name: '${safeName}communication'
  location: 'global'
  properties: {
    dataLocation: 'United States'
  }
}

resource api 'Microsoft.Web/sites@2023-12-01' = {
  name: '${safeName}api'
  location: location
  kind: 'app,linux,container'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'DOCKER|${apiContainerImage}'
      alwaysOn: true
      minTlsVersion: '1.2'
      appSettings: [
        { name: 'APP_ENV', value: 'azure' }
        { name: 'AZURE_FOUNDRY_ENDPOINT', value: foundry.properties.endpoint }
        { name: 'AZURE_USE_MANAGED_IDENTITY', value: 'true' }
        { name: 'AZURE_COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
        { name: 'AZURE_KEY_VAULT_URL', value: vault.properties.vaultUri }
        { name: 'AZURE_SPEECH_REGION', value: location }
        { name: 'AZURE_TRANSLATOR_REGION', value: location }
        { name: 'AZURE_CONTENT_SAFETY_ENDPOINT', value: contentSafety.properties.endpoint }
        { name: 'AZURE_COMMUNICATION_ENDPOINT', value: 'https://${communication.name}.communication.azure.com' }
        { name: 'SMS_SEND_ENABLED', value: 'false' }
        { name: 'SMS_AUTOREPLY_ENABLED', value: 'false' }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }
      ]
    }
  }
}

resource web 'Microsoft.Web/staticSites@2023-12-01' = {
  name: '${namePrefix}-web'
  location: location
  sku: { name: 'Free', tier: 'Free' }
  properties: {
    allowConfigFileUpdates: true
    stagingEnvironmentPolicy: 'Enabled'
  }
}

output apiUrl string = 'https://${api.properties.defaultHostName}'
output staticWebAppName string = web.name
output foundryEndpoint string = foundry.properties.endpoint
output keyVaultUrl string = vault.properties.vaultUri
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output communicationEndpoint string = 'https://${communication.name}.communication.azure.com'
output deploymentNote string = 'Deploy an approved Foundry model, assign managed-identity RBAC, and store service credentials as Key Vault references before production use. SMS remains disabled until a compliant sender is provisioned and explicitly enabled.'
