/// iBreeze Desktop Core 库入口
pub mod commands;
pub mod error;
pub mod keyring;
pub mod rpc;
pub mod store;
pub mod types;

use tauri::Manager;

use crate::commands::*;
use crate::keyring::Keyring;
use crate::rpc::sidecar::SidecarClient;
use crate::store::Store;

pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let sidecar_port = 18900;
            let sidecar = SidecarClient::new(sidecar_port);
            let store = Store::new(std::path::PathBuf::from(
                app.path()
                    .app_data_dir()
                    .unwrap_or_else(|_| std::path::PathBuf::from(".")),
            ));
            let keyring = Keyring::new();

            app.manage(AppState {
                sidecar,
                store,
                keyring,
                auth_token: None,
                current_profile_id: None,
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_profile,
            update_profile,
            list_profiles,
            switch_profile,
            login,
            logout,
            refresh_token,
            create_company,
            list_companies,
            get_company,
            update_company,
            delete_company,
            create_conversation,
            list_conversations,
            get_conversation,
            archive_conversation,
            add_message,
            list_messages,
            create_knowledge_entry,
            list_knowledge_entries,
            search_knowledge,
            create_workspace,
            list_workspaces,
            get_workspace,
            create_orchestration,
            list_orchestrations,
            run_orchestration,
            run_agent,
            list_agents,
            stop_agent,
            generate_keypair,
            sign_data,
            verify_signature,
            check_update,
            apply_update,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
