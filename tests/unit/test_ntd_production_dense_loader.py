import uuid
from unittest.mock import MagicMock

import pytest

from asd_kontur.ntd.production_embedding import EmbeddingProfile
from asd_kontur.ntd.production_query import (
    _DenseCandidate,
    _load_dense_candidates,
    _Profile,
)


@pytest.fixture
def mock_connection():
    return MagicMock()


@pytest.fixture
def valid_profile():
    return _Profile(
        retrieval_profile_id=uuid.uuid4(),
        embedding_profile_id=uuid.uuid4(),
        embedding=EmbeddingProfile(
            key="test",
            version="1.0.0",
            dimension=2,
        ),
        chunk_profile_id=uuid.uuid4(),
        min_relevance=0.18,
    )


def test_load_dense_candidates_valid(mock_connection, valid_profile):
    # Arrange
    chunk_id_1 = uuid.uuid4()
    chunk_id_2 = uuid.uuid4()
    corpus_id_1 = uuid.uuid4()
    corpus_id_2 = uuid.uuid4()

    mock_rows = [
        {
            "corpus_object_id": str(corpus_id_1),
            "contextual_chunk_id": str(chunk_id_1),
            "similarity": 0.95,
            "rank": 1,
        },
        {
            "corpus_object_id": str(corpus_id_2),
            "contextual_chunk_id": str(chunk_id_2),
            "similarity": 0.85,
            "rank": 2,
        },
    ]

    mock_connection.execute.return_value.mappings.return_value.all.return_value = mock_rows

    query_vector = (0.1, 0.2)
    candidate_limit = 10

    # Act
    result = _load_dense_candidates(mock_connection, valid_profile, query_vector, candidate_limit)

    # Assert
    assert len(result) == 2
    assert isinstance(result, tuple)
    assert all(isinstance(c, _DenseCandidate) for c in result)

    # Verify typed values
    assert result[0].corpus_object_id == corpus_id_1
    assert result[0].contextual_chunk_id == chunk_id_1
    assert result[0].similarity == 0.95
    assert result[0].rank == 1

    assert result[1].corpus_object_id == corpus_id_2
    assert result[1].contextual_chunk_id == chunk_id_2
    assert result[1].similarity == 0.85
    assert result[1].rank == 2

    # Verify distinct contextual_chunk_id
    assert result[0].contextual_chunk_id != result[1].contextual_chunk_id

    # Verify SQL and parameters
    mock_connection.execute.assert_called_once()
    call_args = mock_connection.execute.call_args
    sql_obj = call_args[0][0]
    params = call_args[0][1]

    # Check SQL content
    sql_text = sql_obj.text
    assert "platform.ntd_chunk_embeddings" in sql_text
    assert "platform.ntd_contextual_chunks" in sql_text
    assert "platform.ntd_chunks" in sql_text
    assert "e.contextual_chunk_version = cc.version" in sql_text
    assert "cc.chunk_version = c.version" in sql_text

    # Check bound parameters
    expected_vector_literal = "[0.1,0.2]"
    assert params == {
        "query_vector": expected_vector_literal,
        "embedding_profile_id": valid_profile.embedding_profile_id,
        "chunk_profile_id": valid_profile.chunk_profile_id,
        "limit": candidate_limit,
    }


@pytest.mark.parametrize(
    "invalid_limit",
    [True, 0, 201],
    ids=["bool_true", "zero", "over_limit"],
)
def test_load_dense_candidates_invalid_limit(mock_connection, valid_profile, invalid_limit):
    # Act & Assert
    with pytest.raises(ValueError) as exc_info:
        _load_dense_candidates(mock_connection, valid_profile, (0.1, 0.2), invalid_limit)

    # Verify specific error messages based on type/range
    if isinstance(invalid_limit, bool):
        assert exc_info.value.args[0] == "ntd_production_dense_invalid_candidate_limit_type"
    elif invalid_limit == 0:
        assert exc_info.value.args[0] == "ntd_production_dense_invalid_candidate_limit_range"
    elif invalid_limit == 201:
        assert exc_info.value.args[0] == "ntd_production_dense_invalid_candidate_limit_range"

    # Verify execute was not called
    mock_connection.execute.assert_not_called()


def test_load_dense_candidates_invalid_vector_dimension(mock_connection, valid_profile):
    # Arrange
    # valid_profile has dimension 2, so a vector of length 3 is invalid
    invalid_vector = (0.1, 0.2, 0.3)

    # Act & Assert
    with pytest.raises(ValueError) as exc_info:
        _load_dense_candidates(mock_connection, valid_profile, invalid_vector, 10)

    assert exc_info.value.args[0] == "ntd_production_dense_invalid_query_vector_dimension"

    # Verify execute was not called
    mock_connection.execute.assert_not_called()
