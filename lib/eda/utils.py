"""Column selection and data preparation utilities.

Used across all phases for selecting column subsets by dtype,
identifying problematic columns, and basic data cleanup.
"""

import numpy as np
import pandas as pd


def get_numeric_cols(df: pd.DataFrame) -> list[str]:
    """Return list of numeric column names. [eda+]"""
    return df.select_dtypes(include=[np.float64, np.float32, np.int32, np.int64]).columns.tolist()


def get_categorical_cols(df: pd.DataFrame) -> list[str]:
    """Return list of categorical column names. [eda+]"""
    return df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()


def get_nan_cols(df: pd.DataFrame, threshold: float = 0.2) -> list[str]:
    """Return columns where null fraction exceeds threshold. [eda+]"""
    return [col for col in df.columns if df[col].isna().sum() / len(df) > threshold]


def remove_correlated_cols(df: pd.DataFrame, threshold: float = 0.9) -> pd.DataFrame:
    """Drop columns that are highly correlated with another column. [engineer/select]

    Keeps the first column in each correlated pair.
    Used for reducing multicollinearity before modeling.
    """
    corr_matrix = df.select_dtypes(include="number").corr().abs()
    upper = corr_matrix.where(np.triu(np.ones_like(corr_matrix, dtype=bool), k=1))
    to_drop = [col for col in upper.columns if any(upper[col] > threshold)]
    return df.drop(columns=to_drop)


def remove_constant_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Drop columns with only one unique value. [eda+]"""
    return df.loc[:, df.nunique() > 1]
