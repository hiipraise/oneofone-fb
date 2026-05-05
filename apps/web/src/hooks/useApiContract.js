// src/hooks/useApiContract.js
import { useEffect, useState } from 'react'
import { getFrontendContract } from '../services/api'
import { DEFAULT_API_CONTRACT, normalizeContract } from '../config/apiContract'

export function useApiContract() {
  const [contract, setContract] = useState(DEFAULT_API_CONTRACT)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getFrontendContract()
      .then((res) => setContract(normalizeContract(res.data)))
      .catch(() => setContract(DEFAULT_API_CONTRACT))
      .finally(() => setLoading(false))
  }, [])

  return { contract, loading }
}