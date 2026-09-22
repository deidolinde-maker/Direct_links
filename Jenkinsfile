pipeline {
    agent any

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
                    string(credentialsId: 'YANDEX_DIRECT_LOGIN', variable: 'YANDEX_DIRECT_LOGIN'),
                    string(credentialsId: 'YANDEX_DIRECT_TOKEN', variable: 'YANDEX_DIRECT_TOKEN')
                ]) {
                    sh 'python3 --version'
                    sh 'python3 get_campaigns.py'
                    sh 'python3 get_ads.py'
                }
            }
        }
    }
}
