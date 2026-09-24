pipeline {
    agent any

    parameters {
        string(name: 'DIRECT_CAMPAIGN_ID', defaultValue: '109848388', description: 'Campaign ID for targeted Href probe')
    }

    options {
        disableConcurrentBuilds()
        timestamps()
        timeout(time: 10, unit: 'MINUTES')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Run read-only campaigns probe') {
            steps {
                withCredentials([
                    string(credentialsId: 'YANDEX_DIRECT_LOGINS', variable: 'YANDEX_DIRECT_LOGINS'),
                    string(credentialsId: 'YANDEX_DIRECT_TOKEN', variable: 'YANDEX_DIRECT_TOKEN')
                ]) {
                    sh 'python3 --version'
                    // Merge ad-level URLs with campaign-level URLs from Reports.
                    sh 'python3 export_all_urls.py'
                }
            }
        }
    }
}
