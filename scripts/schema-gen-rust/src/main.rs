use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use anyhow::{Context, Result};
use clap::Parser;
use schemars::schema::{RootSchema, Schema, SchemaObject, InstanceType, SingleOrVec};
use walkdir::WalkDir;
use heck::{ToPascalCase, ToSnakeCase};
use quote::{format_ident, quote};
use proc_macro2::TokenStream;

fn rust_field_ident(name: &str) -> proc_macro2::Ident {
    let snake = name.to_snake_case();
    const KEYWORDS: &[&str] = &[
        "as", "async", "await", "break", "const", "continue", "crate", "dyn", "else",
        "enum", "extern", "false", "fn", "for", "if", "impl", "in", "let", "loop",
        "match", "mod", "move", "mut", "pub", "ref", "return", "self", "Self", "static",
        "struct", "super", "trait", "true", "type", "unsafe", "use", "where", "while",
        "abstract", "become", "box", "do", "final", "macro", "override", "priv", "typeof",
        "unsized", "virtual", "yield", "try",
    ];
    if KEYWORDS.contains(&snake.as_str()) {
        format_ident!("r#{}", snake)
    } else {
        format_ident!("{}", snake)
    }
}

#[derive(Parser, Debug)]
#[command(author, version, about = "Generate Rust types from JSON Schema", long_about = None)]
struct Args {
    #[arg(short, long, value_name = "DIR", num_args = 1..)]
    input: Vec<PathBuf>,
    
    #[arg(short, long, value_name = "DIR")]
    output: PathBuf,
    
    #[arg(long, default_value = "ibreeze_contracts")]
    mod_name: String,
}

#[derive(Debug, Clone)]
struct TypeDef {
    name: String,
    tokens: TokenStream,
    is_enum: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();
    
    let mut all_schemas: HashMap<String, RootSchema> = HashMap::new();
    let mut schema_order: Vec<String> = Vec::new();
    
    // Collect all schemas from input directories
    for input_dir in &args.input {
        for entry in WalkDir::new(input_dir)
            .into_iter()
            .filter_entry(|e| {
                e.file_name()
                    .to_str()
                    .map(|s| s != "node_modules" && s != "target" && s != ".git")
                    .unwrap_or(false)
            })
            .filter_map(|e| e.ok())
        {
            let path = entry.path();
            if path.extension().map(|e| e == "json").unwrap_or(false) {
                let content = match fs::read_to_string(path) {
                    Ok(c) => c,
                    Err(_) => continue,
                };
                if !content.contains("\"$schema\"") && !content.contains("\"$id\"") {
                    continue;
                }
                let schema: RootSchema = match serde_json::from_str(&content) {
                    Ok(s) => s,
                    Err(_) => continue,
                };
                
                let id = schema.schema.metadata.as_ref()
                    .and_then(|m| m.id.as_ref())
                    .cloned()
                    .unwrap_or_else(|| path.file_stem().unwrap().to_string_lossy().to_string());
                
                if !all_schemas.contains_key(&id) {
                    schema_order.push(id.clone());
                }
                all_schemas.insert(id, schema);
            }
        }
    }
    
    // Sort deterministically for cross-platform consistency
    schema_order.sort();
    
    // Generate Rust code
    let mut type_defs: Vec<TypeDef> = Vec::new();
    let mut processed: HashMap<String, TypeDef> = HashMap::new();
    
    for id in &schema_order {
        if let Some(schema) = all_schemas.get(id) {
            let def = generate_type_from_schema(id, &schema.schema, &all_schemas, &mut processed)?;
            type_defs.push(def);
        }
    }
    
    // Write output
    let output_dir = &args.output;
    fs::create_dir_all(output_dir)?;
    
    // Generate lib.rs
    let lib_content = generate_lib_rs(&args.mod_name, &type_defs);
    fs::write(output_dir.join("lib.rs"), lib_content)?;
    
    // Generate Cargo.toml for the generated crate
    let cargo_content = generate_cargo_toml(&args.mod_name);
    fs::write(output_dir.join("Cargo.toml"), cargo_content)?;
    
    println!("Generated {} types to {}", type_defs.len(), output_dir.display());
    Ok(())
}

fn generate_type_from_schema(
    schema_id: &str,
    schema: &SchemaObject,
    all_schemas: &HashMap<String, RootSchema>,
    processed: &mut HashMap<String, TypeDef>,
) -> Result<TypeDef> {
    // Check if already processed
    if let Some(existing) = processed.get(schema_id) {
        return Ok(existing.clone());
    }
    
    generate_from_schema_object(schema_id, schema, all_schemas, processed)
}

fn generate_from_schema_object(
    schema_id: &str,
    obj: &SchemaObject,
    all_schemas: &HashMap<String, RootSchema>,
    processed: &mut HashMap<String, TypeDef>,
) -> Result<TypeDef> {
    let type_name = extract_type_name(schema_id);
    
    // Handle references
    if let Some(ref_str) = &obj.reference {
        return resolve_reference(ref_str, all_schemas, processed);
    }
    
    // Handle enums
    if let Some(enum_values) = &obj.enum_values {
        return generate_enum_values(&type_name, enum_values, processed);
    }
    
    // Handle object types
    if matches!(obj.instance_type.as_ref(), Some(SingleOrVec::Single(t)) if **t == InstanceType::Object)
        || obj.object.as_ref().is_some() {
        return generate_struct(&type_name, obj, all_schemas, processed);
    }
    
    // Handle array types
    if matches!(obj.instance_type.as_ref(), Some(SingleOrVec::Single(t)) if **t == InstanceType::Array)
        || obj.array.as_ref().is_some() {
        return generate_array(&type_name, obj, all_schemas, processed);
    }
    
    // Handle primitive types
    generate_primitive(&type_name, obj, processed)
}

fn extract_type_name(schema_id: &str) -> String {
    // Extract a reasonable type name from the schema ID
    let name = schema_id.split('/').last().unwrap_or(schema_id);
    // Remove version suffixes like .v1, .v2
    let name = name.split('.').next().unwrap_or(name);
    name.to_pascal_case()
}

fn resolve_reference(
    ref_str: &str,
    all_schemas: &HashMap<String, RootSchema>,
    processed: &mut HashMap<String, TypeDef>,
) -> Result<TypeDef> {
    // Extract the referenced schema ID from the reference string
    // References can be like "#/definitions/Foo" or external refs
    if ref_str.starts_with("#/") {
        // Local reference - would need to resolve within the same schema
        // For simplicity, return a placeholder
        return Ok(TypeDef {
            name: "LocalRef".to_string(),
            tokens: quote! { serde_json::Value },
            is_enum: false,
        });
    }
    
    // External reference
    if let Some(schema) = all_schemas.get(ref_str) {
        return generate_type_from_schema(ref_str, &schema.schema, all_schemas, processed);
    }
    
    // Try to find by partial match
    for (id, schema) in all_schemas {
        if ref_str.contains(id) || id.contains(ref_str) {
            return generate_type_from_schema(id, &schema.schema, all_schemas, processed);
        }
    }
    
    Ok(TypeDef {
        name: "UnknownRef".to_string(),
        tokens: quote! { serde_json::Value },
        is_enum: false,
    })
}

fn generate_enum_values(
    type_name: &str,
    enum_values: &[serde_json::Value],
    processed: &mut HashMap<String, TypeDef>,
) -> Result<TypeDef> {
    let variants: Vec<TokenStream> = enum_values.iter().map(|v| {
        let variant_name = match v {
            serde_json::Value::String(s) => s.to_pascal_case(),
            serde_json::Value::Number(n) => format!("Value{}", n),
            serde_json::Value::Bool(b) => if *b { "True" } else { "False" }.to_string(),
            _ => "Unknown".to_string(),
        };
        let ident = format_ident!("{}", variant_name);
        quote! { #ident }
    }).collect();
    
    let enum_ident = format_ident!("{}", type_name);
    
    let tokens = quote! {
        #[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
        #[serde(rename_all = "snake_case")]
        pub enum #enum_ident {
            #(#variants),*
        }
    };
    
    let def = TypeDef {
        name: type_name.to_string(),
        tokens,
        is_enum: true,
    };
    processed.insert(type_name.to_string(), def.clone());
    Ok(def)
}

fn generate_struct(
    type_name: &str,
    obj: &SchemaObject,
    all_schemas: &HashMap<String, RootSchema>,
    processed: &mut HashMap<String, TypeDef>,
) -> Result<TypeDef> {
    let mut fields: Vec<TokenStream> = Vec::new();
    let mut required_fields: Vec<String> = Vec::new();
    
    if let Some(object_val) = &obj.object {
        let mut prop_names: Vec<&String> = object_val.properties.keys().collect();
        prop_names.sort();
        for prop_name in prop_names {
            let prop_schema = &object_val.properties[prop_name];
            let is_required = obj.object.as_ref()
                .map(|o| o.required.contains(prop_name.as_str()))
                .unwrap_or(false);
                
                if is_required {
                    required_fields.push(prop_name.clone());
                }
                
                let field_type = schema_to_rust_type(prop_name, &prop_schema, all_schemas, processed)?;
                let field_ident = rust_field_ident(prop_name);
                let serde_name = if *prop_name != prop_name.to_snake_case()
                    || field_ident.to_string().starts_with("r#")
                {
                    quote! { #[serde(rename = #prop_name)] }
                } else {
                    quote! {}
                };
                
                let field = if is_required {
                    quote! {
                        #serde_name
                        pub #field_ident: #field_type,
                    }
                } else {
                    quote! {
                        #serde_name
                        #[serde(skip_serializing_if = "Option::is_none")]
                        pub #field_ident: Option<#field_type>,
                    }
                };
                fields.push(field);
            }
        }
    
    let struct_ident = format_ident!("{}", type_name);
    
    let tokens = quote! {
        #[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
        #[serde(deny_unknown_fields)]
        pub struct #struct_ident {
            #(#fields)*
        }
    };
    
    let def = TypeDef {
        name: type_name.to_string(),
        tokens,
        is_enum: false,
    };
    processed.insert(type_name.to_string(), def.clone());
    Ok(def)
}

fn generate_array(
    type_name: &str,
    obj: &SchemaObject,
    all_schemas: &HashMap<String, RootSchema>,
    processed: &mut HashMap<String, TypeDef>,
) -> Result<TypeDef> {
    let item_type = if let Some(array_val) = &obj.array {
        if let Some(items) = &array_val.items {
            match items {
                SingleOrVec::Single(schema) => schema_to_rust_type("Item", schema, all_schemas, processed)?,
                SingleOrVec::Vec(schemas) => {
                    // Tuple type - use first for simplicity
                    if let Some(first) = schemas.first() {
                        schema_to_rust_type("Item", first, all_schemas, processed)?
                    } else {
                        quote! { serde_json::Value }
                    }
                }
            }
        } else {
            quote! { serde_json::Value }
        }
    } else {
        quote! { serde_json::Value }
    };
    
    let type_ident = format_ident!("{}", type_name);
    let tokens = quote! {
        pub type #type_ident = Vec<#item_type>;
    };
    
    let def = TypeDef {
        name: type_name.to_string(),
        tokens,
        is_enum: false,
    };
    processed.insert(type_name.to_string(), def.clone());
    Ok(def)
}

fn schema_to_rust_type(
    prop_name: &str,
    schema: &Schema,
    all_schemas: &HashMap<String, RootSchema>,
    processed: &mut HashMap<String, TypeDef>,
) -> Result<TokenStream> {
    match schema {
        Schema::Bool(_) => Ok(quote! { serde_json::Value }),
        Schema::Object(obj) => {
            if let Some(ref_str) = &obj.reference {
                // Try to resolve reference
                let type_name = extract_type_name(ref_str);
                let ident = format_ident!("{}", type_name);
                Ok(quote! { #ident })
            } else if let Some(enum_values) = &obj.enum_values {
                // Inline enum
                let type_name = format!("{}{}", prop_name.to_pascal_case(), "Enum");
                let def = generate_enum_values(&type_name, enum_values, processed)?;
                let ident = format_ident!("{}", def.name);
                Ok(quote! { #ident })
            } else if matches!(obj.instance_type.as_ref(), Some(SingleOrVec::Single(t)) if **t == InstanceType::Object)
                || obj.object.is_some() {
                // Inline struct
                let type_name = format!("{}{}", prop_name.to_pascal_case(), "Struct");
                let def = generate_struct(&type_name, obj, all_schemas, processed)?;
                let ident = format_ident!("{}", def.name);
                Ok(quote! { #ident })
            } else if matches!(obj.instance_type.as_ref(), Some(SingleOrVec::Single(t)) if **t == InstanceType::Array)
                || obj.array.is_some() {
                // Inline array
                let item_type = if let Some(array_val) = &obj.array {
                    if let Some(items) = &array_val.items {
                        match items {
                            SingleOrVec::Single(schema) => schema_to_rust_type("Item", schema, all_schemas, processed)?,
                            SingleOrVec::Vec(_) => quote! { serde_json::Value },
                        }
                    } else {
                        quote! { serde_json::Value }
                    }
                } else {
                    quote! { serde_json::Value }
                };
                Ok(quote! { Vec<#item_type> })
            } else {
                generate_primitive_type(obj)
            }
        }
    }
}

fn generate_primitive_type(obj: &SchemaObject) -> Result<TokenStream> {
    let instance_type = obj.instance_type.as_ref()
        .and_then(|t| match t {
            SingleOrVec::Single(t) => Some(&**t),
            SingleOrVec::Vec(t) => t.first(),
        });
    
    let tokens = match instance_type {
        Some(InstanceType::String) => quote! { String },
        Some(&InstanceType::Integer) => quote! { i64 },
        Some(&InstanceType::Number) => quote! { f64 },
        Some(&InstanceType::Boolean) => quote! { bool },
        Some(&InstanceType::Null) => quote! { () },
        _ => quote! { serde_json::Value },
    };
    Ok(tokens)
}

fn generate_primitive(
    type_name: &str,
    obj: &SchemaObject,
    processed: &mut HashMap<String, TypeDef>,
) -> Result<TypeDef> {
    let inner = generate_primitive_type(obj)?;
    let type_ident = format_ident!("{}", type_name);
    let tokens = quote! {
        pub type #type_ident = #inner;
    };
    let def = TypeDef {
        name: type_name.to_string(),
        tokens,
        is_enum: false,
    };
    processed.insert(type_name.to_string(), def.clone());
    Ok(def)
}

fn generate_lib_rs(mod_name: &str, type_defs: &[TypeDef]) -> String {
    let type_items: Vec<TokenStream> = type_defs.iter().map(|d| d.tokens.clone()).collect();
    
    let tokens = quote! {
        //! Generated JSON Schema types for #mod_name
        //! DO NOT EDIT MANUALLY - Generated by schema-gen-rust
        
        #![allow(dead_code, unused_imports, clippy::all)]
        
        use serde::{Deserialize, Serialize};
        
        #(#type_items)*
    };
    
    prettyplease::unparse(&syn::parse2(tokens).unwrap())
}

fn generate_cargo_toml(mod_name: &str) -> String {
    format!(r#"[package]
name = "{}"
version = "0.1.0"
edition = "2021"
description = "Generated JSON Schema types for {}"
license = "MIT"

[dependencies]
serde = {{ version = "1.0", features = ["derive"] }}
serde_json = "1.0"
uuid = {{ version = "1.0", features = ["serde", "v4"] }}
chrono = {{ version = "0.4", features = ["serde"] }}

[profile.release]
lto = true
opt-level = 3
"#, mod_name, mod_name)
}
